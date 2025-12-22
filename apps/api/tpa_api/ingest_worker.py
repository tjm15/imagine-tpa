from __future__ import annotations

import base64
import hashlib
import io
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from celery import Celery

from PIL import Image

from .blob_store import minio_client_or_none, read_blob_bytes, write_blob_bytes
from .db import _db_execute, _db_execute_returning, _db_fetch_all, _db_fetch_one, init_db_pool, shutdown_db_pool
from .evidence import _ensure_evidence_ref_row, _parse_evidence_ref
from .model_clients import _embed_multimodal_sync, _embed_texts_sync, _vlm_json_sync
from .prompting import _llm_structured_sync, _prompt_upsert
from .policy_utils import _normalize_policy_speech_act
from .time_utils import _utc_now, _utc_now_iso
from .vector_utils import _vector_literal
from .services.ingest import (
    _authority_packs_root,
    _derive_filename_for_url,
    _is_http_url,
    _load_authority_pack_manifest,
    _normalize_authority_pack_documents,
    _update_ingest_batch_progress,
    _web_automation_ingest_url,
)


BROKER_URL = os.environ.get("TPA_REDIS_URL") or "redis://localhost:6379/0"
celery_app = Celery("tpa_ingest", broker=BROKER_URL, backend=BROKER_URL)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ensure_artifact(*, artifact_type: str, path: str) -> str:
    existing = _db_fetch_one("SELECT id FROM artifacts WHERE type = %s AND path = %s", (artifact_type, path))
    if existing:
        return str(existing["id"])
    artifact_id = str(uuid4())
    _db_execute(
        "INSERT INTO artifacts (id, type, path) VALUES (%s, %s, %s)",
        (artifact_id, artifact_type, path),
    )
    return artifact_id


def _start_run_step(
    *,
    run_id: str,
    ingest_batch_id: str | None,
    step_name: str,
    inputs: dict[str, Any],
) -> None:
    _db_execute(
        """
        INSERT INTO ingest_run_steps (
          id, ingest_batch_id, run_id, step_name, status, started_at, inputs_jsonb, outputs_jsonb
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s::jsonb, %s::jsonb)
        ON CONFLICT (run_id, step_name)
        DO UPDATE SET status = EXCLUDED.status, started_at = EXCLUDED.started_at, inputs_jsonb = EXCLUDED.inputs_jsonb
        """,
        (
            str(uuid4()),
            ingest_batch_id,
            run_id,
            step_name,
            "running",
            _utc_now(),
            json.dumps(inputs, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
        ),
    )


def _finish_run_step(
    *,
    run_id: str,
    step_name: str,
    status: str,
    outputs: dict[str, Any],
    error_text: str | None = None,
) -> None:
    _db_execute(
        """
        UPDATE ingest_run_steps
        SET status = %s,
            ended_at = %s,
            outputs_jsonb = %s::jsonb,
            error_text = %s
        WHERE run_id = %s::uuid AND step_name = %s
        """,
        (
            status,
            _utc_now(),
            json.dumps(outputs, ensure_ascii=False),
            error_text,
            run_id,
            step_name,
        ),
    )


def _create_ingest_run(
    *,
    ingest_batch_id: str,
    authority_id: str | None,
    plan_cycle_id: str | None,
    inputs: dict[str, Any],
) -> str:
    run_id = str(uuid4())
    pipeline_version = os.environ.get("TPA_INGEST_PIPELINE_VERSION", "v1")
    model_ids = {
        "llm_model_id": os.environ.get("TPA_LLM_MODEL_ID") or os.environ.get("TPA_LLM_MODEL"),
        "vlm_model_id": os.environ.get("TPA_VLM_MODEL_ID"),
        "embeddings_model_id": os.environ.get("TPA_EMBEDDINGS_MODEL_ID"),
        "embeddings_mm_model_id": os.environ.get("TPA_EMBEDDINGS_MM_MODEL_ID"),
        "docparse_provider": os.environ.get("TPA_DOCPARSE_PROVIDER"),
    }
    _db_execute(
        """
        INSERT INTO ingest_runs (
          id, ingest_batch_id, authority_id, plan_cycle_id, pipeline_version,
          model_ids_jsonb, prompt_hashes_jsonb, status, started_at,
          inputs_jsonb, outputs_jsonb
        )
        VALUES (%s, %s::uuid, %s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb, %s::jsonb)
        """,
        (
            run_id,
            ingest_batch_id,
            authority_id,
            plan_cycle_id,
            pipeline_version,
            json.dumps(model_ids, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
            "running",
            _utc_now(),
            json.dumps(inputs or {}, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
        ),
    )
    return run_id


def _finish_ingest_run(
    *,
    run_id: str,
    status: str,
    outputs: dict[str, Any],
    error_text: str | None = None,
) -> None:
    _db_execute(
        """
        UPDATE ingest_runs
        SET status = %s,
            outputs_jsonb = %s::jsonb,
            error_text = %s,
            ended_at = %s
        WHERE id = %s::uuid
        """,
        (
            status,
            json.dumps(outputs, ensure_ascii=False),
            error_text,
            _utc_now(),
            run_id,
        ),
    )


def _set_ingest_run_alias(
    *,
    scope_type: str,
    scope_key: str,
    alias: str,
    run_id: str,
    notes: str | None = None,
) -> None:
    _db_execute(
        """
        INSERT INTO ingest_run_aliases (
          id, scope_type, scope_key, alias, run_id, set_at, set_by, notes
        )
        VALUES (%s, %s, %s, %s, %s::uuid, %s, %s, %s)
        ON CONFLICT (scope_type, scope_key, alias)
        DO UPDATE SET run_id = EXCLUDED.run_id, set_at = EXCLUDED.set_at, set_by = EXCLUDED.set_by, notes = EXCLUDED.notes
        """,
        (str(uuid4()), scope_type, scope_key, alias, run_id, _utc_now(), "system", notes),
    )

def _update_job_status(
    *,
    ingest_job_id: str,
    status: str,
    outputs: dict[str, Any] | None = None,
    error_text: str | None = None,
    started_at: Any | None = None,
    completed_at: Any | None = None,
) -> None:
    _db_execute(
        """
        UPDATE ingest_jobs
        SET status = %s,
            outputs_jsonb = COALESCE(%s::jsonb, outputs_jsonb),
            error_text = %s,
            started_at = COALESCE(%s, started_at),
            completed_at = COALESCE(%s, completed_at)
        WHERE id = %s::uuid
        """,
        (
            status,
            json.dumps(outputs, ensure_ascii=False) if outputs is not None else None,
            error_text,
            started_at,
            completed_at,
            ingest_job_id,
        ),
    )


def _load_parse_bundle(blob_path: str) -> dict[str, Any]:
    client = minio_client_or_none()
    bucket = os.environ.get("TPA_S3_BUCKET")
    if not client or not bucket:
        raise RuntimeError("MinIO not configured for parse bundle retrieval")
    resp = client.get_object(bucket, blob_path)
    try:
        data = resp.read()
    finally:
        resp.close()
        resp.release_conn()
    return json.loads(data)


def _call_docparse_bundle(*, file_bytes: bytes, filename: str, metadata: dict[str, Any]) -> dict[str, Any]:
    base_url = os.environ.get("TPA_DOCPARSE_BASE_URL")
    if not base_url:
        raise RuntimeError("TPA_DOCPARSE_BASE_URL not configured")
    url = base_url.rstrip("/") + "/parse/bundle"
    files = {"file": (filename, io.BytesIO(file_bytes), "application/pdf")}
    data = {"metadata": json.dumps(metadata, ensure_ascii=False)}
    timeout = None
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, files=files, data=data)
        resp.raise_for_status()
        return resp.json()


def _ensure_document_row(
    *,
    authority_id: str,
    plan_cycle_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    blob_path: str,
    metadata: dict[str, Any],
    raw_blob_path: str | None = None,
    raw_sha256: str | None = None,
    raw_bytes: int | None = None,
    raw_content_type: str | None = None,
    raw_source_uri: str | None = None,
    raw_artifact_id: str | None = None,
) -> str:
    existing = None
    if raw_sha256:
        existing = _db_fetch_one(
            """
            SELECT id, raw_blob_path, raw_sha256
            FROM documents
            WHERE authority_id = %s
              AND plan_cycle_id = %s::uuid
              AND raw_sha256 = %s
            """,
            (authority_id, plan_cycle_id, raw_sha256),
        )
    if not existing:
        existing = _db_fetch_one(
            """
            SELECT id FROM documents
            WHERE authority_id = %s
              AND plan_cycle_id = %s::uuid
              AND blob_path = %s
            """,
            (authority_id, plan_cycle_id, blob_path),
        )
    if existing:
        doc_id = str(existing["id"])
        _db_execute(
            """
            UPDATE documents
            SET raw_blob_path = COALESCE(raw_blob_path, %s),
                raw_sha256 = COALESCE(raw_sha256, %s),
                raw_bytes = COALESCE(raw_bytes, %s),
                raw_content_type = COALESCE(raw_content_type, %s),
                raw_source_uri = COALESCE(raw_source_uri, %s),
                raw_artifact_id = COALESCE(raw_artifact_id, %s::uuid),
                run_id = COALESCE(run_id, %s::uuid)
            WHERE id = %s::uuid
            """,
            (raw_blob_path, raw_sha256, raw_bytes, raw_content_type, raw_source_uri, raw_artifact_id, run_id, doc_id),
        )
        return doc_id
    doc_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO documents (
          id, authority_id, ingest_batch_id, plan_cycle_id, run_id,
          document_status, weight_hint, effective_from, effective_to,
          metadata, blob_path, raw_blob_path, raw_sha256, raw_bytes,
          raw_content_type, raw_source_uri, raw_artifact_id
        )
        VALUES (%s, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s::uuid)
        """,
        (
            doc_id,
            authority_id,
            ingest_batch_id,
            plan_cycle_id,
            run_id,
            metadata.get("status"),
            metadata.get("weight_hint"),
            metadata.get("effective_from"),
            metadata.get("effective_to"),
            json.dumps(metadata, ensure_ascii=False),
            blob_path,
            raw_blob_path,
            raw_sha256,
            raw_bytes,
            raw_content_type,
            raw_source_uri,
            raw_artifact_id,
        ),
    )
    return doc_id


def _store_raw_blob(
    *,
    client: Any | None,
    bucket: str | None,
    authority_id: str,
    filename: str,
    data: bytes,
) -> tuple[str, str]:
    sha = _hash_bytes(data)
    ext = Path(filename).suffix or ".pdf"
    object_name = f"raw/{authority_id}/{sha}{ext}"
    if not client or not bucket:
        raise RuntimeError("MinIO not configured for raw artifact storage")
    try:
        client.stat_object(bucket, object_name)
    except Exception:  # noqa: BLE001
        client.put_object(bucket, object_name, io.BytesIO(data), length=len(data), content_type="application/pdf")
    return object_name, sha


def _persist_tool_runs(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    tool_runs: list[dict[str, Any]],
) -> list[str]:
    tool_run_ids: list[str] = []
    for tr in tool_runs:
        tool_run_id = str(uuid4())
        tool_run_ids.append(tool_run_id)
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
              started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                tool_run_id,
                ingest_batch_id,
                run_id,
                tr.get("tool_name") or "docparse_tool",
                json.dumps(tr.get("inputs") or {}, ensure_ascii=False),
                json.dumps(tr.get("outputs") or {}, ensure_ascii=False),
                tr.get("status") or "success",
                _utc_now(),
                _utc_now(),
                tr.get("confidence_hint"),
                tr.get("limitations_text"),
            ),
        )
    return tool_run_ids


def _insert_parse_bundle_record(
    *,
    ingest_job_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    document_id: str,
    schema_version: str,
    blob_path: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    bundle_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO parse_bundles (
          id, ingest_job_id, ingest_batch_id, run_id, document_id,
          schema_version, blob_path, status, metadata_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s::jsonb, %s)
        """,
        (
            bundle_id,
            ingest_job_id,
            ingest_batch_id,
            run_id,
            document_id,
            schema_version,
            blob_path,
            "stored",
            json.dumps(metadata or {}, ensure_ascii=False),
            _utc_now(),
        ),
    )
    return bundle_id


def _persist_pages(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    pages: list[dict[str, Any]],
) -> None:
    for page in pages:
        page_number = int(page.get("page_number") or 0)
        if page_number <= 0:
            continue
        render_blob_path = page.get("render_blob_path")
        render_format = page.get("render_format")
        render_dpi = page.get("render_dpi")
        render_width = page.get("render_width")
        render_height = page.get("render_height")
        render_tier = page.get("render_tier")
        render_reason = page.get("render_reason")
        metadata: dict[str, Any] = {}
        for key in ("width", "height", "text_source", "text_source_reason"):
            if key in page:
                metadata[key] = page.get(key)
        _db_execute(
            """
            INSERT INTO pages (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              render_blob_path, render_format, render_dpi, render_width, render_height,
              render_tier, render_reason, metadata
            )
            VALUES (
              %s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid,
              %s, %s, %s, %s, %s,
              %s, %s, %s::jsonb
            )
            ON CONFLICT (document_id, page_number) DO NOTHING
            """,
            (
                str(uuid4()),
                document_id,
                page_number,
                ingest_batch_id,
                run_id,
                source_artifact_id,
                render_blob_path,
                render_format,
                render_dpi,
                render_width,
                render_height,
                render_tier,
                render_reason,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )


def _persist_bundle_evidence_refs(
    *,
    run_id: str | None,
    evidence_refs: list[dict[str, Any]],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for ref in evidence_refs:
        if not isinstance(ref, dict):
            continue
        source_doc_id = ref.get("source_doc_id")
        section_ref = ref.get("section_ref")
        if not isinstance(source_doc_id, str) or not isinstance(section_ref, str):
            continue
        evidence_ref = f"doc::{source_doc_id}::{section_ref}"
        locator_type = "figure" if section_ref.startswith("visual::") else "paragraph"
        locator_value = section_ref
        evidence_ref_id = _ensure_evidence_ref_row(
            evidence_ref,
            run_id=run_id,
            document_id=source_doc_id,
            locator_type=locator_type,
            locator_value=locator_value,
            excerpt=ref.get("snippet_text"),
        )
        if evidence_ref_id:
            mapping[section_ref] = evidence_ref_id
    return mapping


def _find_span(text: str, fragment: str) -> tuple[int | None, int | None, str]:
    if not text or not fragment:
        return None, None, "none"
    idx = text.find(fragment)
    if idx >= 0:
        return idx, idx + len(fragment), "exact"
    lowered = text.lower()
    frag_lower = fragment.lower()
    idx = lowered.find(frag_lower)
    if idx >= 0:
        return idx, idx + len(fragment), "approx"
    return None, None, "none"


def _find_trigger_spans(text: str, fragment: str) -> list[dict[str, Any]]:
    if not text or not fragment:
        return []
    spans: list[dict[str, Any]] = []
    idx = text.find(fragment)
    if idx >= 0:
        spans.append({"start": idx, "end": idx + len(fragment), "quality": "exact"})
    if spans:
        return spans
    lowered = text.lower()
    frag_lower = fragment.lower()
    start = 0
    while True:
        idx = lowered.find(frag_lower, start)
        if idx < 0:
            break
        spans.append({"start": idx, "end": idx + len(fragment), "quality": "approx"})
        start = idx + len(fragment)
    return spans


def _persist_layout_blocks(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    pages: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    evidence_ref_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    page_texts = {int(p.get("page_number") or 0): str(p.get("text") or "") for p in pages}
    rows: list[dict[str, Any]] = []
    evidence_ref_map = evidence_ref_map or {}
    for block in blocks:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        page_number = int(block.get("page_number") or 0)
        layout_block_id = str(uuid4())
        block_id = str(block.get("block_id") or layout_block_id)
        span_start, span_end, span_quality = _find_span(page_texts.get(page_number, ""), text)
        evidence_ref_id: str | None = None
        used_external_ref = False
        raw_ref = block.get("evidence_ref")
        if isinstance(raw_ref, str):
            parsed = _parse_evidence_ref(raw_ref)
            if parsed:
                evidence_ref_id = evidence_ref_map.get(parsed[2])
                if evidence_ref_id:
                    used_external_ref = True
                else:
                    evidence_ref_id = _ensure_evidence_ref_row(raw_ref, run_id=run_id)
                    used_external_ref = bool(evidence_ref_id)
        if not evidence_ref_id:
            evidence_ref_id = str(uuid4())
        metadata = {}
        raw_meta = block.get("metadata") if isinstance(block.get("metadata"), dict) else {}
        if raw_meta:
            metadata.update(raw_meta)
        if "text_source" in block:
            metadata.setdefault("text_source", block.get("text_source"))
        if "text_source_reason" in block:
            metadata.setdefault("text_source_reason", block.get("text_source_reason"))

        _db_execute(
            """
            INSERT INTO layout_blocks (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              block_id, block_type, text, bbox, bbox_quality, section_path,
              span_start, span_end, span_quality, evidence_ref_id, metadata_jsonb
            )
            VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::uuid, %s::jsonb)
            """,
            (
                layout_block_id,
                document_id,
                page_number,
                ingest_batch_id,
                run_id,
                source_artifact_id,
                block_id,
                block.get("type") or "unknown",
                text,
                json.dumps(block.get("bbox"), ensure_ascii=False) if block.get("bbox") is not None else None,
                block.get("bbox_quality"),
                block.get("section_path"),
                span_start,
                span_end,
                span_quality,
                evidence_ref_id,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        if not used_external_ref:
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (evidence_ref_id, "layout_block", layout_block_id, block_id, run_id),
            )
        evidence_ref_str = raw_ref if isinstance(raw_ref, str) else f"layout_block::{layout_block_id}::{block_id}"
        rows.append(
            {
                "layout_block_id": layout_block_id,
                "block_id": block_id,
                "page_number": page_number,
                "text": text,
                "type": block.get("type"),
                "section_path": block.get("section_path"),
                "bbox": block.get("bbox"),
                "bbox_quality": block.get("bbox_quality"),
                "span_start": span_start,
                "span_end": span_end,
                "span_quality": span_quality,
                "evidence_ref_id": evidence_ref_id,
                "evidence_ref": evidence_ref_str,
            }
        )
    return rows


def _persist_document_tables(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    tables: list[dict[str, Any]],
) -> None:
    for table in tables:
        table_id = str(table.get("table_id") or uuid4())
        page_number = int(table.get("page_number") or 0)
        evidence_ref_id = str(uuid4())
        doc_table_id = str(uuid4())
        _db_execute(
            """
            INSERT INTO document_tables (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              table_id, bbox, bbox_quality, rows_jsonb, evidence_ref_id, metadata_jsonb
            )
            VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s::jsonb, %s::uuid, %s::jsonb)
            """,
            (
                doc_table_id,
                document_id,
                page_number,
                ingest_batch_id,
                run_id,
                source_artifact_id,
                table_id,
                json.dumps(table.get("bbox"), ensure_ascii=False) if table.get("bbox") is not None else None,
                table.get("bbox_quality"),
                json.dumps(table.get("rows") or [], ensure_ascii=False),
                evidence_ref_id,
                json.dumps({}, ensure_ascii=False),
            ),
        )
        _db_execute(
            "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
            (evidence_ref_id, "document_table", doc_table_id, "table", run_id),
        )


def _persist_vector_paths(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    vector_paths: list[dict[str, Any]],
) -> None:
    for path in vector_paths:
        path_id = str(path.get("path_id") or uuid4())
        page_number = int(path.get("page_number") or 0)
        _db_execute(
            """
            INSERT INTO vector_paths (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              path_id, path_type, geometry_jsonb, bbox, bbox_quality, tool_run_id, metadata_jsonb
            )
            VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s::jsonb, %s, %s::uuid, %s::jsonb)
            """,
            (
                str(uuid4()),
                document_id,
                page_number,
                ingest_batch_id,
                run_id,
                source_artifact_id,
                path_id,
                path.get("path_type") or "unknown",
                json.dumps(path.get("geometry"), ensure_ascii=False) if path.get("geometry") is not None else None,
                json.dumps(path.get("bbox"), ensure_ascii=False) if path.get("bbox") is not None else None,
                path.get("bbox_quality"),
                None,
                json.dumps({}, ensure_ascii=False),
            ),
        )


def _persist_chunks_from_blocks(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    block_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    chunk_rows: list[dict[str, Any]] = []
    for block in block_rows:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        chunk_id = str(uuid4())
        page_number = block.get("page_number")
        fragment = str(block.get("block_id") or "block")
        evidence_ref_id = block.get("evidence_ref_id")
        if not evidence_ref_id:
            evidence_ref_id = str(uuid4())
        _db_execute(
            """
            INSERT INTO chunks (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              text, bbox, bbox_quality, type, section_path, span_start, span_end,
              span_quality, evidence_ref_id, metadata
            )
            VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s, %s, %s, %s, %s::uuid, %s::jsonb)
            """,
            (
                chunk_id,
                document_id,
                page_number,
                ingest_batch_id,
                run_id,
                source_artifact_id,
                text,
                json.dumps(block.get("bbox"), ensure_ascii=False) if block.get("bbox") is not None else None,
                block.get("bbox_quality"),
                block.get("type"),
                block.get("section_path"),
                block.get("span_start"),
                block.get("span_end"),
                block.get("span_quality"),
                evidence_ref_id,
                json.dumps({"evidence_ref_fragment": fragment}, ensure_ascii=False),
            ),
        )
        if evidence_ref_id and not block.get("evidence_ref_id"):
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (evidence_ref_id, "chunk", chunk_id, fragment, run_id),
            )
        chunk_rows.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "page_number": page_number,
                "fragment": fragment,
                "evidence_ref": block.get("evidence_ref") or f"chunk::{chunk_id}::{fragment}",
                "type": block.get("type"),
                "section_path": block.get("section_path"),
                "span_start": block.get("span_start"),
                "span_end": block.get("span_end"),
                "evidence_ref_id": evidence_ref_id,
            }
        )
    return chunk_rows


def _persist_visual_assets(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    visual_assets: list[dict[str, Any]],
    evidence_ref_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    evidence_ref_map = evidence_ref_map or {}
    for asset in visual_assets:
        asset_id = str(uuid4())
        blob_path = asset.get("blob_path")
        if not isinstance(blob_path, str) or not blob_path:
            continue
        metadata = {
            "asset_type": asset.get("asset_type"),
            "role": asset.get("role"),
            "classification": asset.get("classification") or {},
            "metrics": asset.get("metrics") or [],
            "caption": asset.get("caption"),
            "width": asset.get("width"),
            "height": asset.get("height"),
            "source_asset_id": asset.get("asset_id"),
        }
        now = _utc_now()
        evidence_ref_id: str | None = None
        source_asset_id = asset.get("asset_id")
        if isinstance(source_asset_id, str) and source_asset_id:
            fragment = f"visual::{source_asset_id}"
            evidence_ref_id = evidence_ref_map.get(fragment)
            if not evidence_ref_id:
                evidence_ref = f"doc::{document_id}::{fragment}"
                evidence_ref_id = _ensure_evidence_ref_row(evidence_ref, run_id=run_id)
            if not evidence_ref_id:
                evidence_ref_id = str(uuid4())
                _db_execute(
                    """
                    INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id)
                    VALUES (%s, %s, %s, %s, %s::uuid)
                    """,
                    (evidence_ref_id, "visual_asset", asset_id, "image", run_id),
                )
        _db_execute(
            """
            INSERT INTO visual_assets (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              asset_type, blob_path, evidence_ref_id, metadata, created_at, updated_at
            )
            VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s::uuid, %s::jsonb, %s, %s)
            """,
            (
                asset_id,
                document_id,
                asset.get("page_number"),
                ingest_batch_id,
                run_id,
                source_artifact_id,
                asset.get("asset_type") or "unknown",
                blob_path,
                evidence_ref_id,
                json.dumps(metadata, ensure_ascii=False),
                now,
                now,
            ),
        )
        rows.append(
            {
                "visual_asset_id": asset_id,
                "page_number": asset.get("page_number"),
                "metadata": metadata,
                "blob_path": blob_path,
                "evidence_ref_id": evidence_ref_id,
                "source_asset_id": asset.get("asset_id"),
            }
        )
    return rows


def _persist_visual_features(*, visual_assets: list[dict[str, Any]], run_id: str | None) -> None:
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        if not visual_asset_id:
            continue
        metadata = asset.get("metadata") or {}
        classification = metadata.get("classification") or {}
        feature_type = classification.get("asset_type") or "visual_classification"
        _db_execute(
            """
            INSERT INTO visual_features (
              id, visual_asset_id, run_id, feature_type,
              geometry_jsonb, confidence, evidence_ref_id, metadata_jsonb
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s::uuid, %s::jsonb)
            """,
            (
                str(uuid4()),
                visual_asset_id,
                run_id,
                feature_type,
                None,
                None,
                asset.get("evidence_ref_id"),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )


def _persist_visual_semantic_features(
    *,
    visual_assets: list[dict[str, Any]],
    semantic: dict[str, Any],
    run_id: str | None,
) -> None:
    if not semantic:
        return
    blob_map = {row.get("blob_path"): row for row in visual_assets if row.get("blob_path")}

    constraints = semantic.get("visual_constraints") if isinstance(semantic.get("visual_constraints"), list) else []
    for vc in constraints:
        if not isinstance(vc, dict):
            continue
        image_ref = vc.get("image_ref")
        row = blob_map.get(image_ref)
        if not row:
            continue
        _db_execute(
            """
            INSERT INTO visual_features (
              id, visual_asset_id, run_id, feature_type,
              geometry_jsonb, confidence, evidence_ref_id, metadata_jsonb
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s::uuid, %s::jsonb)
            """,
            (
                str(uuid4()),
                row.get("visual_asset_id"),
                run_id,
                "visual_constraint",
                None,
                None,
                row.get("evidence_ref_id"),
                json.dumps(vc, ensure_ascii=False),
            ),
        )


def _run_vlm_structured(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    tool_name: str,
    prompt_id: str,
    prompt_version: int,
    prompt_name: str,
    purpose: str,
    prompt: str,
    image_bytes: bytes,
    model_id: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    tool_run_id = str(uuid4())
    started_at = _utc_now()
    _prompt_upsert(
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        name=prompt_name,
        purpose=purpose,
        template=prompt,
        input_schema_ref=None,
        output_schema_ref=None,
    )
    _db_execute(
        """
        INSERT INTO tool_runs (
          id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
          started_at, ended_at, confidence_hint, uncertainty_note
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, %s, %s)
        """,
        (
            tool_run_id,
            ingest_batch_id,
            run_id,
            tool_name,
            json.dumps(
                {
                    "prompt_id": prompt_id,
                    "prompt_version": prompt_version,
                    "prompt_name": prompt_name,
                    "purpose": purpose,
                    "model_id": model_id,
                    "prompt": prompt,
                },
                ensure_ascii=False,
            ),
            json.dumps({}, ensure_ascii=False),
            "running",
            started_at,
            "medium",
            "VLM output is non-deterministic; verify limitations and trace to tool runs.",
        ),
    )

    obj, errs = _vlm_json_sync(prompt=prompt, image_bytes=image_bytes, model_id=model_id)
    status = "success" if obj is not None and not errs else ("partial" if obj is not None else "error")
    _db_execute(
        """
        UPDATE tool_runs
        SET status = %s, outputs_logged = %s::jsonb, ended_at = %s
        WHERE id = %s::uuid
        """,
        (
            status,
            json.dumps({"ok": obj is not None, "errors": errs[:10], "parsed_json": obj}, ensure_ascii=False),
            _utc_now(),
            tool_run_id,
        ),
    )
    return obj, tool_run_id, errs


def _upsert_visual_semantic_output(
    *,
    visual_asset_id: str,
    run_id: str | None,
    schema_version: str,
    output_kind: str = "classification",
    tool_run_id: str | None,
    asset_type: str | None = None,
    asset_subtype: str | None = None,
    canonical_facts: dict[str, Any] | None = None,
    asset_specific_facts: dict[str, Any] | None = None,
    assertions: list[dict[str, Any]] | None = None,
    agent_findings: dict[str, Any] | None = None,
    material_index: dict[str, Any] | None = None,
    metadata_update: dict[str, Any] | None = None,
) -> None:
    existing = _db_fetch_one(
        """
        SELECT id, metadata_jsonb
        FROM visual_semantic_outputs
        WHERE visual_asset_id = %s::uuid
          AND (%s::uuid IS NULL OR run_id = %s::uuid)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (visual_asset_id, run_id, run_id),
    )
    if existing and existing.get("id"):
        metadata = existing.get("metadata_jsonb") if isinstance(existing.get("metadata_jsonb"), dict) else {}
        if metadata_update:
            metadata.update(metadata_update)
        _db_execute(
            """
            UPDATE visual_semantic_outputs
            SET output_kind = COALESCE(%s, output_kind),
                asset_type = COALESCE(%s, asset_type),
                asset_subtype = COALESCE(%s, asset_subtype),
                canonical_facts_jsonb = COALESCE(%s::jsonb, canonical_facts_jsonb),
                asset_specific_facts_jsonb = COALESCE(%s::jsonb, asset_specific_facts_jsonb),
                assertions_jsonb = COALESCE(%s::jsonb, assertions_jsonb),
                agent_findings_jsonb = COALESCE(%s::jsonb, agent_findings_jsonb),
                material_index_jsonb = COALESCE(%s::jsonb, material_index_jsonb),
                metadata_jsonb = %s::jsonb,
                tool_run_id = COALESCE(%s::uuid, tool_run_id)
            WHERE id = %s::uuid
            """,
            (
                output_kind,
                asset_type,
                asset_subtype,
                json.dumps(canonical_facts, ensure_ascii=False) if canonical_facts is not None else None,
                json.dumps(asset_specific_facts, ensure_ascii=False) if asset_specific_facts is not None else None,
                json.dumps(assertions, ensure_ascii=False) if assertions is not None else None,
                json.dumps(agent_findings, ensure_ascii=False) if agent_findings is not None else None,
                json.dumps(material_index, ensure_ascii=False) if material_index is not None else None,
                json.dumps(metadata, ensure_ascii=False),
                tool_run_id,
                existing["id"],
            ),
        )
        return

    _db_execute(
        """
        INSERT INTO visual_semantic_outputs (
          id, visual_asset_id, run_id, schema_version, output_kind, asset_type, asset_subtype,
          canonical_facts_jsonb, asset_specific_facts_jsonb, assertions_jsonb,
          agent_findings_jsonb, material_index_jsonb, metadata_jsonb, tool_run_id, created_at
        )
        VALUES (
          %s, %s::uuid, %s::uuid, %s, %s, %s, %s,
          %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::uuid, %s
        )
        """,
        (
            str(uuid4()),
            visual_asset_id,
            run_id,
            schema_version,
            output_kind,
            asset_type,
            asset_subtype,
            json.dumps(canonical_facts or {}, ensure_ascii=False),
            json.dumps(asset_specific_facts or {}, ensure_ascii=False),
            json.dumps(assertions or [], ensure_ascii=False),
            json.dumps(agent_findings or {}, ensure_ascii=False),
            json.dumps(material_index or {}, ensure_ascii=False),
            json.dumps(metadata_update or {}, ensure_ascii=False),
            tool_run_id,
            _utc_now(),
        ),
    )


def _extract_visual_asset_facts(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
) -> int:
    if not visual_assets:
        return 0

    asset_types = [
        "photo_existing",
        "photomontage",
        "render_cgi",
        "streetscape_montage",
        "location_plan",
        "site_plan_existing",
        "site_plan_proposed",
        "floor_plan",
        "roof_plan",
        "elevation",
        "section",
        "axonometric_or_3d",
        "diagram_access_transport",
        "diagram_landscape_trees",
        "diagram_daylight_sunlight",
        "diagram_heritage_townscape",
        "diagram_flood_drainage",
        "diagram_phasing_construction",
        "design_material_palette",
        "other_diagram",
    ]

    prompt_id = "visual_asset_facts_v1"
    inserted = 0
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        blob_path = asset.get("blob_path")
        if not visual_asset_id or not isinstance(blob_path, str):
            continue
        image_bytes, _, err = read_blob_bytes(blob_path)
        if err or not image_bytes:
            raise RuntimeError(f"visual_asset_read_failed:{err or 'no_bytes'}")

        metadata = asset.get("metadata") or {}
        asset_type_hint = metadata.get("asset_type") or "unknown"
        prompt = (
            "You are a planning visual parsing instrument. Return ONLY valid JSON.\n"
            "Choose asset_type from: "
            + ", ".join(asset_types)
            + ".\n"
            "Output shape:\n"
            "{\n"
            '  "asset_type": "...",\n'
            '  "asset_subtype": "...|null",\n'
            '  "canonical_visual_facts": {\n'
            '    "depiction": {"depiction_kind": "photo|drawing|map|diagram|render|mixed", "view_kind": "plan|section|elevation|perspective|axonometric|unknown", "composite_indicator": {"likely_composite": true, "confidence": 0.0}},\n'
            '    "orientation": {"north_arrow_present": true, "north_bearing_degrees": 0, "confidence": 0.0},\n'
            '    "scale_signals": {"scale_bar_present": true, "written_scale_present": true, "dimensions_present": true, "known_object_scale_cues": [], "confidence": 0.0},\n'
            '    "boundary_representation": {"site_boundary_present": true, "boundary_style": "redline|blue_line|dashed|unknown", "confidence": 0.0},\n'
            '    "annotations": {"legend_present": true, "key_present": true, "labels_legible": true, "critical_notes_present": true, "confidence": 0.0},\n'
            '    "viewpoint": {"viewpoint_applicable": true, "declared_viewpoint_present": false, "estimated_camera_height_m": null, "estimated_lens_equiv_mm": null, "estimated_view_direction_degrees": null, "confidence": 0.0},\n'
            '    "height_and_levels": {"height_markers_present": true, "level_datums_present": true, "storey_indicators_present": true, "confidence": 0.0}\n'
            "  },\n"
            '  "asset_specific_facts": {...}\n'
            "}\n"
            f"Asset type hint: {asset_type_hint}.\n"
            "Emit only the asset_specific_facts block relevant to the asset_type."
        )

        obj, tool_run_id, _ = _run_vlm_structured(
            ingest_batch_id=ingest_batch_id,
            run_id=run_id,
            tool_name="vlm_visual_asset_facts",
            prompt_id=prompt_id,
            prompt_version=1,
            prompt_name="Visual asset facts",
            purpose="Extract canonical and asset-specific facts from a visual asset.",
            prompt=prompt,
            image_bytes=image_bytes,
        )
        if not isinstance(obj, dict):
            continue

        asset_type = obj.get("asset_type") if isinstance(obj.get("asset_type"), str) else None
        asset_subtype = obj.get("asset_subtype") if isinstance(obj.get("asset_subtype"), str) else None
        canonical_facts = obj.get("canonical_visual_facts") if isinstance(obj.get("canonical_visual_facts"), dict) else {}
        asset_specific = obj.get("asset_specific_facts") if isinstance(obj.get("asset_specific_facts"), dict) else {}

        _upsert_visual_semantic_output(
            visual_asset_id=visual_asset_id,
            run_id=run_id,
            schema_version="1.0",
            output_kind="classification",
            tool_run_id=tool_run_id,
            asset_type=asset_type,
            asset_subtype=asset_subtype,
            canonical_facts=canonical_facts,
            asset_specific_facts=asset_specific,
            metadata_update={"asset_facts_tool_run_id": tool_run_id},
        )
        if asset_type or asset_subtype:
            _update_visual_asset_identity(
                visual_asset_id=visual_asset_id,
                asset_type=asset_type,
                asset_subtype=asset_subtype,
            )
            _merge_visual_asset_metadata(
                visual_asset_id=visual_asset_id,
                patch={
                    "asset_type_vlm": asset_type,
                    "asset_subtype_vlm": asset_subtype,
                    "asset_type_source": "vlm_asset_facts",
                },
            )
            asset_meta = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            asset_meta["asset_type_vlm"] = asset_type
            asset_meta["asset_subtype_vlm"] = asset_subtype
            asset_meta["asset_type_source"] = "vlm_asset_facts"
            asset["metadata"] = asset_meta
            asset["asset_type"] = asset_type
        inserted += 1

    return inserted


def _build_material_index(assertions: list[dict[str, Any]]) -> dict[str, Any]:
    index: dict[str, dict[str, Any]] = {}
    for assertion in assertions:
        tags = assertion.get("material_consideration_tags") if isinstance(assertion, dict) else None
        assertion_id = assertion.get("assertion_id") if isinstance(assertion, dict) else None
        if not isinstance(tags, list) or not assertion_id:
            continue
        for tag in tags:
            if not isinstance(tag, str):
                continue
            entry = index.setdefault(tag, {"assertion_ids": [], "agent_mentions": []})
            entry["assertion_ids"].append(assertion_id)
    return index


def _extract_visual_region_assertions(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
) -> int:
    if not visual_assets:
        return 0

    prompt_id = "visual_region_assertions_v1"
    total_assertions = 0
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        if not visual_asset_id:
            continue
        semantic_row = _db_fetch_one(
            """
            SELECT canonical_facts_jsonb, asset_specific_facts_jsonb, asset_type, asset_subtype, metadata_jsonb
            FROM visual_semantic_outputs
            WHERE visual_asset_id = %s::uuid
              AND (%s::uuid IS NULL OR run_id = %s::uuid)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (visual_asset_id, run_id, run_id),
        )
        canonical_facts = semantic_row.get("canonical_facts_jsonb") if isinstance(semantic_row, dict) else {}
        asset_specific = semantic_row.get("asset_specific_facts_jsonb") if isinstance(semantic_row, dict) else {}
        asset_type = semantic_row.get("asset_type") if isinstance(semantic_row, dict) else None
        asset_subtype = semantic_row.get("asset_subtype") if isinstance(semantic_row, dict) else None

        region_rows = _db_fetch_all(
            """
            SELECT id, bbox, bbox_quality, caption_text, metadata_jsonb
            FROM visual_asset_regions
            WHERE visual_asset_id = %s::uuid
              AND (%s::uuid IS NULL OR run_id = %s::uuid)
            ORDER BY created_at
            """,
            (visual_asset_id, run_id, run_id),
        )
        if not region_rows:
            continue

        assertions: list[dict[str, Any]] = []
        for region in region_rows:
            region_id = str(region.get("id"))
            meta = region.get("metadata_jsonb") if isinstance(region.get("metadata_jsonb"), dict) else {}
            region_blob_path = meta.get("region_blob_path")
            region_evidence_ref = meta.get("evidence_ref")
            if not isinstance(region_blob_path, str):
                continue
            image_bytes, _, err = read_blob_bytes(region_blob_path)
            if err or not image_bytes:
                continue

            prompt = (
                "You are a planning visual assertion instrument. Return ONLY valid JSON.\n"
                "Given a cropped region from a planning visual, produce atomic assertions anchored to this region.\n"
                "Do NOT assess policy compliance or planning balance; describe what the region appears to show or claim.\n"
                "Output shape:\n"
                "{\n"
                '  "assertions": [\n'
                "    {\n"
                '      "assertion_id": "uuid",\n'
                '      "assertion_type": "string",\n'
                '      "statement": "string",\n'
                '      "polarity": "supports|raises_risk|neutral",\n'
                '      "basis": ["string"],\n'
                '      "confidence": 0.0,\n'
                '      "risk_flags": ["string"],\n'
                '      "material_consideration_tags": ["string"],\n'
                '      "follow_up_requests": ["string"],\n'
                f'      "evidence_region_id": "{region_id}"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "Use assertion_type from this vocabulary when possible:\n"
                "design_scale_massing, design_form_roofline, design_materiality, design_frontage_and_activation,\n"
                "design_rhythm_grain, townscape_subordination_or_dominance, townscape_skyline_effect,\n"
                "townscape_view_corridor_effect, townscape_street_enclosure, heritage_setting_effect,\n"
                "heritage_harm_signal, heritage_view_of_designated_asset, amenity_overlooking_signal,\n"
                "amenity_enclosure_outlook_signal, amenity_daylight_sunlight_signal, amenity_noise_activity_signal,\n"
                "access_point_and_visibility_signal, servicing_feasibility_signal, parking_cycle_provision_signal,\n"
                "trees_retention_or_loss_signal, landscape_character_signal, drainage_strategy_signal, flood_risk_signal,\n"
                "context_omission_risk, scale_presentation_risk, idealisation_risk, viewpoint_bias_risk.\n"
                "Material consideration tags should be chosen from:\n"
                "design.scale_massing, design.form_roofline, design.materials_detailing, design.public_realm_frontage,\n"
                "townscape.character_appearance, townscape.views_skyline, townscape.street_enclosure,\n"
                "heritage.setting_significance, heritage.views_assets,\n"
                "amenity.privacy_overlooking, amenity.daylight_sunlight, amenity.outlook_enclosure,\n"
                "transport.access_highway_safety, transport.parking_cycle, transport.servicing,\n"
                "landscape.trees_planting, landscape.open_space, ecology.habitat_cues,\n"
                "water.flood_risk, water.drainage_suds, construction.phasing_logistics,\n"
                "evidence.representation_limits.\n"
                f"Asset type: {asset_type or 'unknown'}; asset subtype: {asset_subtype or 'null'}.\n"
                f"Canonical facts: {json.dumps(canonical_facts, ensure_ascii=False)}\n"
                f"Asset-specific facts: {json.dumps(asset_specific, ensure_ascii=False)}\n"
                f"Region bbox: {json.dumps(region.get('bbox'), ensure_ascii=False)}\n"
                f"Region caption: {region.get('caption_text') or ''}\n"
            )

            obj, tool_run_id, _ = _run_vlm_structured(
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                tool_name="vlm_region_assertions",
                prompt_id=prompt_id,
                prompt_version=1,
                prompt_name="Region assertions",
                purpose="Extract region-level assertions from a visual crop.",
                prompt=prompt,
                image_bytes=image_bytes,
            )
            if not isinstance(obj, dict):
                continue
            region_assertions = obj.get("assertions") if isinstance(obj.get("assertions"), list) else []
            for a in region_assertions:
                if not isinstance(a, dict):
                    continue
                assertion_id = a.get("assertion_id")
                try:
                    if not isinstance(assertion_id, str):
                        raise ValueError("invalid")
                    UUID(assertion_id)
                except Exception:  # noqa: BLE001
                    assertion_id = str(uuid4())
                a["assertion_id"] = assertion_id
                if not a.get("evidence_region_id"):
                    a["evidence_region_id"] = region_id
                if isinstance(region_evidence_ref, str) and region_evidence_ref:
                    a["evidence_region_ref"] = region_evidence_ref
                assertions.append(a)
            total_assertions += len(region_assertions)

        material_index = _build_material_index(assertions)
        _upsert_visual_semantic_output(
            visual_asset_id=visual_asset_id,
            run_id=run_id,
            schema_version="1.0",
            output_kind="classification",
            tool_run_id=None,
            assertions=assertions,
            material_index=material_index,
            metadata_update={"region_assertions_count": len(assertions)},
        )

    return total_assertions


def _extract_visual_agent_findings(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
) -> int:
    if not visual_assets:
        return 0

    system_template = (
        "You are a planning specialist review panel. Return ONLY valid JSON with the shape:\n"
        "{\n"
        '  "agent_findings": {\n'
        '    "Design & Character Agent": {\n'
        '      "agent_name": "Design & Character Agent",\n'
        '      "scope_tags": ["design.scale_massing", "design.form_roofline", "design.materials_detailing", "design.public_realm_frontage"],\n'
        '      "supported_assertions": [{"assertion_id": "uuid", "commentary": "string", "confidence_adjustment": -0.2}],\n'
        '      "challenged_assertions": [{"assertion_id": "uuid", "commentary": "string", "confidence_adjustment": -0.2, "additional_risk_flags": ["string"]}],\n'
        '      "additional_assertions": [ {"assertion_id": "uuid", "assertion_type": "string", "statement": "string", "polarity": "supports|raises_risk|neutral", "basis": ["string"], "confidence": 0.0, "risk_flags": ["string"], "material_consideration_tags": ["string"], "follow_up_requests": ["string"]} ],\n'
        '      "notable_omissions": ["string"]\n'
        "    },\n"
        '    "Townscape & Visual Impact Agent": { ... },\n'
        '    "Heritage & Setting Agent": { ... },\n'
        '    "Residential Amenity Agent": { ... },\n'
        '    "Access, Parking & Servicing Agent": { ... },\n'
        '    "Landscape & Trees Agent": { ... },\n'
        '    "Water, Flood & Drainage Agent": { ... },\n'
        '    "Representation Integrity Agent": { ... }\n'
        "  }\n"
        "}\n"
        "Rules:\n"
        "- Only reference assertion_id values that exist in the provided assertions list.\n"
        "- If there is nothing to add, return empty arrays and empty omissions.\n"
        "- Keep commentary concise and in officer-report language.\n"
        "- Do not decide compliance or planning balance; focus on evidence quality and visual signals.\n"
    )

    updated = 0
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        if not visual_asset_id:
            continue
        semantic_row = _db_fetch_one(
            """
            SELECT canonical_facts_jsonb, asset_specific_facts_jsonb, asset_type, asset_subtype, assertions_jsonb
            FROM visual_semantic_outputs
            WHERE visual_asset_id = %s::uuid
              AND (%s::uuid IS NULL OR run_id = %s::uuid)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (visual_asset_id, run_id, run_id),
        )
        if not isinstance(semantic_row, dict):
            continue
        assertions = semantic_row.get("assertions_jsonb") if isinstance(semantic_row.get("assertions_jsonb"), list) else []
        if not assertions:
            continue
        canonical_facts = semantic_row.get("canonical_facts_jsonb") if isinstance(semantic_row.get("canonical_facts_jsonb"), dict) else {}
        asset_specific = semantic_row.get("asset_specific_facts_jsonb") if isinstance(semantic_row.get("asset_specific_facts_jsonb"), dict) else {}
        asset_type = semantic_row.get("asset_type") if isinstance(semantic_row.get("asset_type"), str) else None
        asset_subtype = semantic_row.get("asset_subtype") if isinstance(semantic_row.get("asset_subtype"), str) else None

        obj, tool_run_id, _ = _llm_structured_sync(
            prompt_id="visual_agent_findings_v1",
            prompt_version=1,
            prompt_name="Visual agent findings",
            purpose="Review visual assertions with specialist planning lenses.",
            system_template=system_template,
            user_payload={
                "asset_type": asset_type,
                "asset_subtype": asset_subtype,
                "canonical_facts": canonical_facts,
                "asset_specific_facts": asset_specific,
                "assertions": assertions,
            },
            time_budget_seconds=120.0,
            output_schema_ref=None,
            ingest_batch_id=ingest_batch_id,
            run_id=run_id,
        )
        if not isinstance(obj, dict) or not isinstance(obj.get("agent_findings"), dict):
            continue
        agent_findings = obj.get("agent_findings") or {}
        if isinstance(agent_findings, dict):
            for agent in agent_findings.values():
                if not isinstance(agent, dict):
                    continue
                additional = agent.get("additional_assertions")
                if isinstance(additional, list):
                    for extra in additional:
                        if not isinstance(extra, dict):
                            continue
                        assertion_id = extra.get("assertion_id")
                        try:
                            if not isinstance(assertion_id, str):
                                raise ValueError("invalid")
                            UUID(assertion_id)
                        except Exception:  # noqa: BLE001
                            assertion_id = str(uuid4())
                        extra["assertion_id"] = assertion_id

        _upsert_visual_semantic_output(
            visual_asset_id=visual_asset_id,
            run_id=run_id,
            schema_version="1.0",
            output_kind="classification",
            tool_run_id=tool_run_id,
            agent_findings=agent_findings,
            metadata_update={"agent_findings_tool_run_id": tool_run_id},
        )
        updated += 1

    return updated

def _decode_base64_payload(data: str) -> bytes:
    if "base64," in data:
        data = data.split("base64,", 1)[1]
    return base64.b64decode(data)


def _mask_png_to_rle(mask_png_bytes: bytes) -> dict[str, Any] | None:
    try:
        with Image.open(io.BytesIO(mask_png_bytes)) as img:
            if img.mode == "RGBA":
                alpha = img.split()[-1]
                pixels = list(alpha.getdata())
            else:
                img = img.convert("L")
                pixels = list(img.getdata())
            width, height = img.size
    except Exception:  # noqa: BLE001
        return None

    counts: list[int] = []
    last = 0
    run_len = 0
    for val in pixels:
        bit = 1 if val > 0 else 0
        if bit != last:
            counts.append(run_len)
            run_len = 0
            last = bit
        run_len += 1
    counts.append(run_len)
    return {"size": [height, width], "counts": counts}


def _truncate_text(text: str | None, limit: int) -> str:
    if not text:
        return ""
    cleaned = str(text)
    return cleaned if len(cleaned) <= limit else cleaned[:limit].rstrip() + "..."


def _bbox_from_geometry(geometry: dict[str, Any] | None) -> list[float] | None:
    if not isinstance(geometry, dict):
        return None
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")
    points: list[tuple[float, float]] = []

    def _collect_ring(ring: Any) -> None:
        if isinstance(ring, list):
            for pt in ring:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    try:
                        points.append((float(pt[0]), float(pt[1])))
                    except Exception:  # noqa: BLE001
                        continue

    if geom_type == "Polygon" and isinstance(coords, list):
        for ring in coords:
            _collect_ring(ring)
    elif geom_type == "MultiPolygon" and isinstance(coords, list):
        for poly in coords:
            if isinstance(poly, list):
                for ring in poly:
                    _collect_ring(ring)
    else:
        return None

    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _vectorize_segmentation_masks(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    document_id: str,
    visual_assets: list[dict[str, Any]],
) -> int:
    base_url = os.environ.get("TPA_VECTORIZE_BASE_URL")
    if not base_url:
        raise RuntimeError("vectorize_unconfigured")
    timeout = None

    asset_ids = [a.get("visual_asset_id") for a in visual_assets if a.get("visual_asset_id")]
    if not asset_ids:
        return 0
    page_by_asset = {a.get("visual_asset_id"): int(a.get("page_number") or 0) for a in visual_assets}

    mask_rows = _db_fetch_all(
        """
        SELECT id, visual_asset_id, mask_artifact_path, bbox, label
        FROM segmentation_masks
        WHERE visual_asset_id = ANY(%s::uuid[])
          AND (%s::uuid IS NULL OR run_id = %s::uuid)
        ORDER BY created_at
        """,
        (asset_ids, run_id, run_id),
    )
    if not mask_rows:
        return 0

    path_total = 0
    for mask in mask_rows:
        mask_id = str(mask.get("id"))
        visual_asset_id = mask.get("visual_asset_id")
        if not visual_asset_id:
            continue
        mask_path = mask.get("mask_artifact_path")
        if not isinstance(mask_path, str):
            continue
        mask_bytes, _, err = read_blob_bytes(mask_path)
        if err or not mask_bytes:
            raise RuntimeError(f"mask_read_failed:{err or 'no_bytes'}")

        tool_run_id = str(uuid4())
        started = _utc_now()
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
              started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, %s, %s)
            """,
            (
                tool_run_id,
                ingest_batch_id,
                run_id,
                "vectorize_mask",
                json.dumps(
                    {"visual_asset_id": visual_asset_id, "mask_id": mask_id, "mask_path": mask_path},
                    ensure_ascii=False,
                ),
                json.dumps({}, ensure_ascii=False),
                "running",
                started,
                "medium",
                "Vectorization requested; awaiting response.",
            ),
        )

        payload = {"mask_png_base64": base64.b64encode(mask_bytes).decode("ascii")}
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(base_url.rstrip("/") + "/vectorize", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            _db_execute(
                "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
                ("error", json.dumps({"error": str(exc)}, ensure_ascii=False), _utc_now(), tool_run_id),
            )
            raise RuntimeError(f"vectorize_failed:{exc}") from exc

        features_geojson = data.get("features_geojson") if isinstance(data, dict) else None
        features = features_geojson.get("features") if isinstance(features_geojson, dict) else None
        if not isinstance(features, list):
            _db_execute(
                "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
                (
                    "error",
                    json.dumps({"error": "vectorize_invalid_response"}, ensure_ascii=False),
                    _utc_now(),
                    tool_run_id,
                ),
            )
            raise RuntimeError("vectorize_invalid_response")

        insert_count = 0
        for idx, feature in enumerate(features, start=1):
            if not isinstance(feature, dict):
                continue
            geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else None
            if not geometry:
                continue
            bbox = _bbox_from_geometry(geometry) or mask.get("bbox")
            bbox_quality = "exact" if bbox else "none"
            path_id = f"vm-{mask_id}-{idx:03d}"
            path_type = None
            props = feature.get("properties") if isinstance(feature.get("properties"), dict) else None
            if props:
                path_type = props.get("source")
            if not isinstance(path_type, str) or not path_type:
                path_type = "mask_contour"
            _db_execute(
                """
                INSERT INTO vector_paths (
                  id, document_id, page_number, ingest_batch_id, source_artifact_id,
                  path_id, path_type, geometry_jsonb, bbox, bbox_quality, tool_run_id, metadata_jsonb
                )
                VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s::jsonb, %s, %s::uuid, %s::jsonb)
                """,
                (
                    str(uuid4()),
                    document_id,
                    page_by_asset.get(visual_asset_id, 0),
                    ingest_batch_id,
                    None,
                    path_id,
                    path_type,
                    json.dumps(geometry, ensure_ascii=False),
                    json.dumps(bbox, ensure_ascii=False) if bbox else None,
                    bbox_quality,
                    tool_run_id,
                    json.dumps(
                        {
                            "coord_space": "image_pixels",
                            "vector_source": "segmentation_mask",
                            "visual_asset_id": visual_asset_id,
                            "mask_id": mask_id,
                            "mask_label": mask.get("label"),
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            insert_count += 1

        _db_execute(
            "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
            (
                "success",
                json.dumps({"path_count": insert_count}, ensure_ascii=False),
                _utc_now(),
                tool_run_id,
            ),
        )
        path_total += insert_count

    return path_total

def _segment_visual_assets(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    authority_id: str,
    plan_cycle_id: str | None,
    document_id: str,
    visual_assets: list[dict[str, Any]],
) -> tuple[int, int]:
    base_url = os.environ.get("TPA_SEGMENTATION_BASE_URL")
    if not base_url:
        raise RuntimeError("segmentation_unconfigured")
    timeout = None
    prefix = f"docparse/{authority_id}/{plan_cycle_id or 'none'}/{document_id}"

    mask_total = 0
    region_total = 0
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        blob_path = asset.get("blob_path")
        if not visual_asset_id or not isinstance(blob_path, str):
            continue

        image_bytes, _, err = read_blob_bytes(blob_path)
        if err or not image_bytes:
            raise RuntimeError(f"visual_asset_read_failed:{err or 'no_bytes'}")

        tool_run_id = str(uuid4())
        started = _utc_now()
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
              started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, %s, %s)
            """,
            (
                tool_run_id,
                ingest_batch_id,
                run_id,
                "segment_visual_asset",
                json.dumps({"visual_asset_id": visual_asset_id, "blob_path": blob_path}, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                "running",
                started,
                "medium",
                "Segmentation requested; awaiting response.",
            ),
        )

        payload = {"image_base64": base64.b64encode(image_bytes).decode("ascii"), "prompts": None}
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(base_url.rstrip("/") + "/segment", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            _db_execute(
                "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
                ("error", json.dumps({"error": str(exc)}, ensure_ascii=False), _utc_now(), tool_run_id),
            )
            raise RuntimeError(f"segmentation_failed:{exc}") from exc

        masks = data.get("masks") if isinstance(data, dict) else None
        limitations_text = data.get("limitations_text") if isinstance(data, dict) else None
        if not isinstance(masks, list) or not masks:
            _db_execute(
                "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
                (
                    "error",
                    json.dumps({"error": "no_masks_returned", "limitations_text": limitations_text}, ensure_ascii=False),
                    _utc_now(),
                    tool_run_id,
                ),
            )
            raise RuntimeError("segmentation_no_masks")

        caption = (asset.get("metadata") or {}).get("caption")
        for idx, mask in enumerate(masks, start=1):
            if not isinstance(mask, dict):
                continue
            mask_b64 = mask.get("mask_png_base64")
            if not isinstance(mask_b64, str):
                raise RuntimeError("mask_payload_invalid")
            mask_bytes = _decode_base64_payload(mask_b64)
            mask_rle = _mask_png_to_rle(mask_bytes)
            if mask_rle is None:
                raise RuntimeError("mask_rle_failed")

            mask_blob_path = f"{prefix}/visual_masks/{visual_asset_id}/mask-{idx:03d}.png"
            stored_path, store_err = write_blob_bytes(mask_blob_path, mask_bytes, content_type="image/png")
            if store_err or not stored_path:
                raise RuntimeError(f"mask_upload_failed:{store_err}")

            bbox = mask.get("bbox")
            bbox_quality = "exact" if isinstance(bbox, list) and len(bbox) == 4 else "none"
            mask_id = str(uuid4())
            _db_execute(
                """
                INSERT INTO segmentation_masks (
                  id, visual_asset_id, run_id, label, prompt, mask_artifact_path, mask_rle_jsonb,
                  bbox, bbox_quality, confidence, tool_run_id, created_at
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s::uuid, %s)
                """,
                (
                    mask_id,
                    visual_asset_id,
                    run_id,
                    mask.get("label"),
                    mask.get("prompt"),
                    stored_path,
                    json.dumps(mask_rle, ensure_ascii=False),
                    json.dumps(bbox, ensure_ascii=False) if bbox else None,
                    bbox_quality,
                    mask.get("confidence"),
                    tool_run_id,
                    _utc_now(),
                ),
            )
            mask_total += 1

            region_blob_path = None
            if isinstance(bbox, list) and len(bbox) == 4:
                try:
                    x0, y0, x1, y1 = [int(float(v)) for v in bbox]
                    if x1 > x0 and y1 > y0:
                        with Image.open(io.BytesIO(image_bytes)) as img:
                            crop = img.crop((x0, y0, x1, y1))
                            out = io.BytesIO()
                            crop.save(out, format="PNG")
                            region_blob_path = f"{prefix}/visual_regions/{visual_asset_id}/region-{idx:03d}.png"
                            stored_region, region_err = write_blob_bytes(region_blob_path, out.getvalue(), content_type="image/png")
                            if region_err:
                                raise RuntimeError(region_err)
                            region_blob_path = stored_region
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(f"region_crop_failed:{exc}") from exc

            region_id = str(uuid4())
            region_evidence_ref = f"visual_region::{region_id}::crop"
            region_evidence_ref_id = _ensure_evidence_ref_row(region_evidence_ref, run_id=run_id)
            region_meta = {
                "region_blob_path": region_blob_path,
                "polygon": mask.get("polygon"),
                "confidence": mask.get("confidence"),
                "evidence_ref": region_evidence_ref,
            }
            _db_execute(
                """
                INSERT INTO visual_asset_regions (
                  id, visual_asset_id, run_id, region_type, bbox, bbox_quality,
                  mask_id, caption_text, evidence_ref_id, metadata_jsonb, created_at
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s::uuid, %s, %s::uuid, %s::jsonb, %s)
                """,
                (
                    region_id,
                    visual_asset_id,
                    run_id,
                    "mask_crop",
                    json.dumps(bbox, ensure_ascii=False) if bbox else None,
                    bbox_quality,
                    mask_id,
                    caption,
                    region_evidence_ref_id,
                    json.dumps(region_meta, ensure_ascii=False),
                    _utc_now(),
                ),
            )
            region_total += 1

        _db_execute(
            "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s, uncertainty_note = %s WHERE id = %s::uuid",
            (
                "success",
                json.dumps({"mask_count": len(masks), "visual_asset_id": visual_asset_id}, ensure_ascii=False),
                _utc_now(),
                limitations_text,
                tool_run_id,
            ),
        )

    return mask_total, region_total


def _should_attempt_georef(asset_type: str | None, canonical_facts: dict[str, Any]) -> bool:
    if isinstance(asset_type, str):
        normalized = asset_type.strip().lower()
        if normalized in {
            "location_plan",
            "site_plan_existing",
            "site_plan_proposed",
            "diagram_access_transport",
            "diagram_landscape_trees",
            "diagram_daylight_sunlight",
            "diagram_heritage_townscape",
            "diagram_flood_drainage",
            "diagram_phasing_construction",
        }:
            return True
    depiction = canonical_facts.get("depiction") if isinstance(canonical_facts, dict) else None
    if isinstance(depiction, dict):
        if depiction.get("depiction_kind") == "map":
            return True
    return False


def _merge_visual_asset_metadata(*, visual_asset_id: str, patch: dict[str, Any]) -> None:
    _db_execute(
        """
        UPDATE visual_assets
        SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
            updated_at = NOW()
        WHERE id = %s::uuid
        """,
        (json.dumps(patch, ensure_ascii=False), visual_asset_id),
    )


def _update_visual_asset_identity(
    *,
    visual_asset_id: str,
    asset_type: str | None,
    asset_subtype: str | None,
) -> None:
    if not asset_type and not asset_subtype:
        return
    patch: dict[str, Any] = {}
    if asset_type:
        patch["asset_type"] = asset_type
    if asset_subtype:
        patch["asset_subtype"] = asset_subtype
    _db_execute(
        """
        UPDATE visual_assets
        SET asset_type = COALESCE(%s, asset_type),
            metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
            updated_at = NOW()
        WHERE id = %s::uuid
        """,
        (asset_type, json.dumps(patch, ensure_ascii=False), visual_asset_id),
    )


def _ensure_world_frame(*, epsg: int) -> str:
    row = _db_fetch_one(
        "SELECT id FROM frames WHERE frame_type = %s AND epsg = %s",
        ("world", epsg),
    )
    if row:
        return str(row["id"])
    frame_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO frames (id, frame_type, epsg, description, metadata_jsonb, created_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        """,
        (frame_id, "world", epsg, f"EPSG:{epsg}", json.dumps({}, ensure_ascii=False), _utc_now()),
    )
    return frame_id


def _create_image_frame(*, visual_asset_id: str, blob_path: str, page_number: int | None) -> str:
    frame_id = str(uuid4())
    metadata = {"visual_asset_id": visual_asset_id, "blob_path": blob_path, "page_number": page_number}
    _db_execute(
        """
        INSERT INTO frames (id, frame_type, epsg, description, metadata_jsonb, created_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        """,
        (
            frame_id,
            "image",
            None,
            f"visual_asset::{visual_asset_id}",
            json.dumps(metadata, ensure_ascii=False),
            _utc_now(),
        ),
    )
    return frame_id


def _persist_georef_outputs(
    *,
    run_id: str | None,
    tool_run_id: str,
    image_frame_id: str,
    target_epsg: int,
    payload: dict[str, Any],
) -> tuple[str | None, int, int, list[str]]:
    errors: list[str] = []
    transform_id: str | None = None
    transform_count = 0
    projection_count = 0

    transform = payload.get("transform") if isinstance(payload, dict) else None
    control_points = payload.get("control_points") if isinstance(payload, dict) else None
    if not isinstance(control_points, list) and isinstance(transform, dict):
        control_points = transform.get("control_points")

    if isinstance(transform, dict):
        matrix = transform.get("matrix")
        matrix_shape = transform.get("matrix_shape")
        method = transform.get("method") if isinstance(transform.get("method"), str) else "unknown"
        uncertainty_score = transform.get("uncertainty_score")
        if isinstance(matrix, list) and isinstance(matrix_shape, list):
            world_frame_id = _ensure_world_frame(epsg=target_epsg)
            transform_id = str(uuid4())
            cp_ids: list[str] = []
            if isinstance(control_points, list):
                for cp in control_points:
                    if not isinstance(cp, dict):
                        continue
                    cp_id = str(uuid4())
                    cp_ids.append(cp_id)
            _db_execute(
                """
                INSERT INTO transforms (
                  id, from_frame_id, to_frame_id, method, matrix, matrix_shape,
                  uncertainty_score, control_point_ids_jsonb, tool_run_id, metadata_jsonb, created_at
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s::uuid, %s::jsonb, %s)
                """,
                (
                    transform_id,
                    image_frame_id,
                    world_frame_id,
                    method,
                    json.dumps(matrix, ensure_ascii=False),
                    json.dumps(matrix_shape, ensure_ascii=False),
                    float(uncertainty_score) if isinstance(uncertainty_score, (int, float)) else None,
                    json.dumps(cp_ids, ensure_ascii=False),
                    tool_run_id,
                    json.dumps(transform.get("metadata") if isinstance(transform.get("metadata"), dict) else {}, ensure_ascii=False),
                    _utc_now(),
                ),
            )
            transform_count += 1

            if isinstance(control_points, list):
                for cp_id, cp in zip(cp_ids, control_points, strict=False):
                    if not isinstance(cp, dict):
                        continue
                    _db_execute(
                        """
                        INSERT INTO control_points (id, transform_id, src_jsonb, dst_jsonb, residual, weight, created_at)
                        VALUES (%s, %s::uuid, %s::jsonb, %s::jsonb, %s, %s, %s)
                        """,
                        (
                            cp_id,
                            transform_id,
                            json.dumps(cp.get("src") or {}, ensure_ascii=False),
                            json.dumps(cp.get("dst") or {}, ensure_ascii=False),
                            float(cp.get("residual")) if isinstance(cp.get("residual"), (int, float)) else None,
                            float(cp.get("weight")) if isinstance(cp.get("weight"), (int, float)) else None,
                            _utc_now(),
                        ),
                    )
        else:
            errors.append("transform_missing_matrix")
    else:
        errors.append("transform_missing")

    artifacts = payload.get("projection_artifacts") if isinstance(payload, dict) else None
    if isinstance(artifacts, list):
        for art in artifacts:
            if not isinstance(art, dict):
                continue
            artifact_path = art.get("artifact_path") or art.get("path")
            if not isinstance(artifact_path, str) or not artifact_path:
                continue
            evidence_ref = art.get("evidence_ref")
            evidence_ref_id = None
            if isinstance(evidence_ref, str) and evidence_ref:
                evidence_ref_id = _ensure_evidence_ref_row(evidence_ref, run_id=run_id)
            _db_execute(
                """
                INSERT INTO projection_artifacts (
                  id, transform_id, artifact_type, artifact_path, evidence_ref_id, tool_run_id, metadata_jsonb, created_at
                )
                VALUES (%s, %s::uuid, %s, %s, %s::uuid, %s::uuid, %s::jsonb, %s)
                """,
                (
                    str(uuid4()),
                    transform_id,
                    art.get("artifact_type") if isinstance(art.get("artifact_type"), str) else "image_overlay",
                    artifact_path,
                    evidence_ref_id,
                    tool_run_id,
                    json.dumps(art.get("metadata") if isinstance(art.get("metadata"), dict) else {}, ensure_ascii=False),
                    _utc_now(),
                ),
            )
            projection_count += 1

    return transform_id, transform_count, projection_count, errors


def _auto_georef_visual_assets(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
    target_epsg: int,
) -> tuple[int, int, int, int]:
    base_url = os.environ.get("TPA_GEOREF_BASE_URL")
    attempts = 0
    successes = 0
    transform_count = 0
    projection_count = 0

    asset_ids = [a.get("visual_asset_id") for a in visual_assets if a.get("visual_asset_id")]
    semantic_rows = []
    if asset_ids:
        semantic_rows = _db_fetch_all(
            """
            SELECT DISTINCT ON (visual_asset_id)
              visual_asset_id, asset_type, asset_subtype, canonical_facts_jsonb, asset_specific_facts_jsonb
            FROM visual_semantic_outputs
            WHERE visual_asset_id = ANY(%s::uuid[])
              AND (%s::uuid IS NULL OR run_id = %s::uuid)
            ORDER BY visual_asset_id, created_at DESC
            """,
            (asset_ids, run_id, run_id),
        )
    semantic_by_id = {str(r.get("visual_asset_id")): r for r in semantic_rows if r.get("visual_asset_id")}

    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        blob_path = asset.get("blob_path")
        if not visual_asset_id or not isinstance(blob_path, str):
            continue

        semantic_row = semantic_by_id.get(visual_asset_id) or {}
        asset_type = semantic_row.get("asset_type") if isinstance(semantic_row.get("asset_type"), str) else None
        asset_subtype = semantic_row.get("asset_subtype") if isinstance(semantic_row.get("asset_subtype"), str) else None
        if not asset_type or not asset_subtype:
            meta = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            if not asset_type and isinstance(meta.get("asset_type"), str):
                asset_type = meta.get("asset_type")
            if not asset_subtype and isinstance(meta.get("asset_subtype"), str):
                asset_subtype = meta.get("asset_subtype")
        canonical_facts = semantic_row.get("canonical_facts_jsonb") if isinstance(semantic_row.get("canonical_facts_jsonb"), dict) else {}
        asset_specific = semantic_row.get("asset_specific_facts_jsonb") if isinstance(semantic_row.get("asset_specific_facts_jsonb"), dict) else {}

        if not _should_attempt_georef(asset_type, canonical_facts):
            continue

        attempts += 1
        tool_run_id = str(uuid4())
        started = _utc_now()
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
              started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, %s, %s)
            """,
            (
                tool_run_id,
                ingest_batch_id,
                run_id,
                "auto_georef",
                json.dumps(
                    {
                        "visual_asset_id": visual_asset_id,
                        "blob_path": blob_path,
                        "asset_type": asset_type,
                        "asset_subtype": asset_subtype,
                        "target_epsg": target_epsg,
                    },
                    ensure_ascii=False,
                ),
                json.dumps({}, ensure_ascii=False),
                "running",
                started,
                "medium",
                "Auto-georeferencing attempted; downstream overlays are best-effort.",
            ),
        )

        page_number = asset.get("page_number") if isinstance(asset.get("page_number"), int) else None
        image_frame_id = _create_image_frame(visual_asset_id=visual_asset_id, blob_path=blob_path, page_number=page_number)
        _merge_visual_asset_metadata(
            visual_asset_id=visual_asset_id,
            patch={"image_frame_id": image_frame_id, "georef_tool_run_id": tool_run_id, "georef_status": "running"},
        )

        if not base_url:
            _db_execute(
                "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
                ("error", json.dumps({"error": "georef_unconfigured"}, ensure_ascii=False), _utc_now(), tool_run_id),
            )
            _merge_visual_asset_metadata(
                visual_asset_id=visual_asset_id,
                patch={"georef_status": "unconfigured"},
            )
            continue

        image_bytes, _, err = read_blob_bytes(blob_path)
        if err or not image_bytes:
            _db_execute(
                "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
                ("error", json.dumps({"error": f"visual_asset_read_failed:{err or 'no_bytes'}"}, ensure_ascii=False), _utc_now(), tool_run_id),
            )
            _merge_visual_asset_metadata(
                visual_asset_id=visual_asset_id,
                patch={"georef_status": "error", "georef_error": "visual_asset_read_failed"},
            )
            continue

        payload = {
            "visual_asset_id": visual_asset_id,
            "asset_type": asset_type,
            "asset_subtype": asset_subtype,
            "target_epsg": target_epsg,
            "image_base64": base64.b64encode(image_bytes).decode("ascii"),
            "canonical_facts": canonical_facts,
            "asset_specific_facts": asset_specific,
        }
        try:
            with httpx.Client(timeout=None) as client:
                resp = client.post(base_url.rstrip("/") + "/auto-georef", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            _db_execute(
                "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
                ("error", json.dumps({"error": str(exc)}, ensure_ascii=False), _utc_now(), tool_run_id),
            )
            _merge_visual_asset_metadata(
                visual_asset_id=visual_asset_id,
                patch={"georef_status": "error", "georef_error": str(exc)},
            )
            continue

        if not isinstance(data, dict):
            _db_execute(
                "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
                ("error", json.dumps({"error": "georef_invalid_response"}, ensure_ascii=False), _utc_now(), tool_run_id),
            )
            _merge_visual_asset_metadata(
                visual_asset_id=visual_asset_id,
                patch={"georef_status": "error", "georef_error": "invalid_response"},
            )
            continue

        data_status = data.get("status") if isinstance(data.get("status"), str) else None
        transform_id, t_count, p_count, georef_errors = _persist_georef_outputs(
            run_id=run_id,
            tool_run_id=tool_run_id,
            image_frame_id=image_frame_id,
            target_epsg=target_epsg,
            payload=data,
        )
        transform_count += t_count
        projection_count += p_count
        if transform_id or p_count > 0 or data.get("ok") is True:
            successes += 1
            _merge_visual_asset_metadata(
                visual_asset_id=visual_asset_id,
                patch={
                    "georef_status": "success",
                    "transform_id": transform_id,
                    "projection_artifact_count": p_count,
                },
            )
            status = "success" if not georef_errors else "partial"
        else:
            _merge_visual_asset_metadata(
                visual_asset_id=visual_asset_id,
                patch={
                    "georef_status": data_status or "error",
                    "georef_error": "no_transform",
                },
            )
            status = "error"

        _db_execute(
            "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
            (
                status,
                json.dumps(
                    {
                        "ok": data.get("ok") if isinstance(data.get("ok"), bool) else None,
                        "transform_id": transform_id,
                        "projection_artifact_count": p_count,
                        "status": data_status,
                        "errors": georef_errors[:10],
                    },
                    ensure_ascii=False,
                ),
                _utc_now(),
                tool_run_id,
            ),
        )

    return attempts, successes, transform_count, projection_count


def _propose_visual_policy_links(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
    policy_headings: list[dict[str, Any]],
    page_texts: dict[int, str],
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    if not visual_assets or not policy_headings:
        return {}, 0

    candidates_all = [
        {
            "policy_code": h.get("policy_code"),
            "title": h.get("policy_title"),
            "evidence_ref": h.get("evidence_ref"),
        }
        for h in policy_headings
        if h.get("policy_code")
    ]
    if not candidates_all:
        return {}, 0

    prompt_id = "visual_asset_link_v2"
    proposals_by_asset: dict[str, list[dict[str, Any]]] = {}
    proposal_count = 0

    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        blob_path = asset.get("blob_path")
        if not visual_asset_id or not isinstance(blob_path, str):
            continue
        metadata = asset.get("metadata") or {}
        page_number = int(asset.get("page_number") or 0)
        caption = metadata.get("caption") or (metadata.get("classification") or {}).get("caption_hint")
        page_text = _truncate_text(page_texts.get(page_number), 1200)
        asset_type = metadata.get("asset_type") or metadata.get("asset_type_vlm") or (metadata.get("classification") or {}).get("asset_type")
        semantic_row = _db_fetch_one(
            """
            SELECT asset_type, asset_subtype
            FROM visual_semantic_outputs
            WHERE visual_asset_id = %s::uuid
              AND (%s::uuid IS NULL OR run_id = %s::uuid)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (visual_asset_id, run_id, run_id),
        )
        if semantic_row and not asset_type:
            asset_type = semantic_row.get("asset_type")
        asset_subtype = semantic_row.get("asset_subtype") if semantic_row else None

        image_bytes, _, err = read_blob_bytes(blob_path)
        if err or not image_bytes:
            raise RuntimeError(f"visual_asset_read_failed:{err or 'no_bytes'}")

        prompt = (
            "You are a planning visual linker. Return ONLY valid JSON.\n"
            "Text may appear inside the image; use it if present. Some links are implied by the visual content.\n"
            "Only link to policies listed in policy_candidates. Do not invent codes.\n"
            "Output shape:\n"
            '{ "links": [ { "policy_code": "string", "confidence": "low|medium|high", '
            '"rationale": "string", "basis": "in_image_text|caption|visual_implied|page_context" } ] }\n'
            f"Asset type: {asset_type or 'unknown'}.\n"
            f"Asset subtype: {asset_subtype or 'unknown'}.\n"
            f"Caption (if any): {caption or ''}\n"
            f"Page text (if any): {page_text or ''}\n"
            f"Policy candidates: {json.dumps(candidates_all, ensure_ascii=False)}\n"
        )

        obj, tool_run_id, errs = _run_vlm_structured(
            prompt_id=prompt_id,
            prompt_version=2,
            prompt_name="Visual policy linker",
            purpose="Link visual assets to relevant policy sections using the visual content.",
            tool_name="vlm_visual_policy_link",
            prompt=prompt,
            image_bytes=image_bytes,
            ingest_batch_id=ingest_batch_id,
            run_id=run_id,
        )
        if errs or not isinstance(obj, dict):
            raise RuntimeError(f"visual_link_failed:{errs or 'invalid_response'}")

        links = obj.get("links")
        if not isinstance(links, list):
            continue
        for link in links:
            if not isinstance(link, dict):
                continue
            policy_code = link.get("policy_code")
            if not isinstance(policy_code, str):
                continue
            proposals_by_asset.setdefault(visual_asset_id, []).append(
                {
                    "policy_code": policy_code,
                    "confidence": link.get("confidence"),
                    "rationale": link.get("rationale"),
                    "basis": link.get("basis") or "unspecified",
                    "candidate_scope": "all",
                    "page_number": page_number,
                    "tool_run_id": tool_run_id,
                }
            )
            proposal_count += 1

    return proposals_by_asset, proposal_count


def _persist_visual_policy_links_from_proposals(
    *,
    run_id: str | None,
    proposals_by_asset: dict[str, list[dict[str, Any]]],
    visual_assets: list[dict[str, Any]],
    policy_sections: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], int]:
    if not proposals_by_asset:
        return {}, 0
    section_by_code = {
        str(s.get("policy_code")).strip(): s
        for s in policy_sections
        if isinstance(s.get("policy_code"), str)
    }
    section_by_title = {
        str(s.get("title")).strip().lower(): s
        for s in policy_sections
        if isinstance(s.get("title"), str)
    }
    evidence_by_asset = {row.get("visual_asset_id"): row.get("evidence_ref_id") for row in visual_assets}
    links_by_asset: dict[str, list[str]] = {}
    link_count = 0

    for asset_id, proposals in proposals_by_asset.items():
        for link in proposals:
            policy_code = link.get("policy_code")
            section = None
            if isinstance(policy_code, str):
                section = section_by_code.get(policy_code.strip()) or section_by_code.get(policy_code.strip().upper())
                if not section:
                    section = section_by_title.get(policy_code.strip().lower())
            if not section:
                continue
            section_id = section.get("policy_section_id")
            if not section_id:
                continue
            _db_execute(
                """
                INSERT INTO visual_asset_links (
                  id, visual_asset_id, run_id, target_type, target_id, link_type,
                  evidence_ref_id, tool_run_id, metadata_jsonb, created_at
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s::uuid, %s::uuid, %s::jsonb, %s)
                """,
                (
                    str(uuid4()),
                    asset_id,
                    run_id,
                    "policy_section",
                    str(section_id),
                    "policy_reference",
                    evidence_by_asset.get(asset_id),
                    link.get("tool_run_id"),
                    json.dumps(
                        {
                            "policy_code": section.get("policy_code"),
                            "policy_title": section.get("title"),
                            "confidence": link.get("confidence"),
                            "rationale": link.get("rationale"),
                            "basis": link.get("basis") or "unspecified",
                            "candidate_scope": link.get("candidate_scope") or "all",
                            "page_number": link.get("page_number"),
                        },
                        ensure_ascii=False,
                    ),
                    _utc_now(),
                ),
            )
            links_by_asset.setdefault(asset_id, []).append(str(section_id))
            link_count += 1

    return links_by_asset, link_count


def _embed_visual_assets(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
    policy_sections: list[dict[str, Any]],
    links_by_asset: dict[str, list[str]],
) -> int:
    if not visual_assets:
        return 0
    model_id = os.environ.get("TPA_EMBEDDINGS_MM_MODEL_ID", "nomic-ai/colnomic-embed-multimodal-7b")
    tool_run_id = str(uuid4())
    started = _utc_now()
    _db_execute(
        """
        INSERT INTO tool_runs (
          id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
          started_at, ended_at, confidence_hint, uncertainty_note
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, %s, %s)
        """,
        (
            tool_run_id,
            ingest_batch_id,
            run_id,
            "embed_visual_assets",
            json.dumps({"asset_count": len(visual_assets), "model_id": model_id}, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
            "running",
            started,
            "medium",
            "Embedding visual assets with policy-linked context.",
        ),
    )

    sections_by_id = {s.get("policy_section_id"): s for s in policy_sections if s.get("policy_section_id")}
    inserted = 0
    skipped = 0
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        blob_path = asset.get("blob_path")
        if not visual_asset_id or not isinstance(blob_path, str):
            continue
        linked = links_by_asset.get(visual_asset_id) or []
        if not linked:
            skipped += 1
            continue
        image_bytes, _, err = read_blob_bytes(blob_path)
        if err or not image_bytes:
            raise RuntimeError(f"visual_asset_read_failed:{err or 'no_bytes'}")

        metadata = asset.get("metadata") or {}
        caption = metadata.get("caption") or (metadata.get("classification") or {}).get("caption_hint")
        context_lines = []
        if caption:
            context_lines.append(f"Caption: {caption}")
        if metadata.get("asset_type"):
            context_lines.append(f"Asset type: {metadata.get('asset_type')}")
        for section_id in linked:
            section = sections_by_id.get(section_id) or {}
            code = section.get("policy_code") or "policy"
            title = section.get("title") or ""
            context_lines.append(f"Policy {code}: {title}".strip())
            context_lines.append(_truncate_text(section.get("text"), 800))
        context_text = "\n".join([line for line in context_lines if line]).strip()
        if not context_text:
            skipped += 1
            continue

        vec = _embed_multimodal_sync(image_bytes=image_bytes, text=context_text, model_id=model_id)
        if not vec:
            _db_execute(
                "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
                (
                    "error",
                    json.dumps({"error": "visual_embedding_failed", "visual_asset_id": visual_asset_id}, ensure_ascii=False),
                    _utc_now(),
                    tool_run_id,
                ),
            )
            raise RuntimeError("visual_embedding_failed")

        _db_execute(
            """
            INSERT INTO unit_embeddings (
              id, unit_type, unit_id, embedding, embedding_model_id, embedding_dim, created_at, tool_run_id, run_id
            )
            VALUES (%s, %s, %s::uuid, %s::vector, %s, %s, %s, %s::uuid, %s::uuid)
            ON CONFLICT (unit_type, unit_id, embedding_model_id) DO NOTHING
            """,
            (
                str(uuid4()),
                "visual_asset",
                visual_asset_id,
                _vector_literal(vec),
                model_id,
                len(vec),
                _utc_now(),
                tool_run_id,
                run_id,
            ),
        )
        inserted += 1

    _db_execute(
        "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
        (
            "success" if inserted > 0 or skipped > 0 else "error",
            json.dumps({"inserted": inserted, "skipped": skipped}, ensure_ascii=False),
            _utc_now(),
            tool_run_id,
        ),
    )
    return inserted


def _embed_visual_assertions(*, ingest_batch_id: str, run_id: str | None) -> int:
    rows = _db_fetch_all(
        """
        SELECT id, assertions_jsonb
        FROM visual_semantic_outputs
        WHERE (%s::uuid IS NULL OR run_id = %s::uuid)
        """,
        (run_id, run_id),
    )
    candidates: list[tuple[str, str]] = []
    for row in rows:
        assertions = row.get("assertions_jsonb") if isinstance(row.get("assertions_jsonb"), list) else []
        for assertion in assertions:
            if not isinstance(assertion, dict):
                continue
            assertion_id = assertion.get("assertion_id")
            statement = assertion.get("statement")
            if not isinstance(assertion_id, str) or not isinstance(statement, str) or not statement.strip():
                continue
            try:
                UUID(assertion_id)
            except Exception:  # noqa: BLE001
                continue
            candidates.append((assertion_id, statement.strip()))
    if not candidates:
        return 0

    texts = [text for _, text in candidates]
    embeddings = _embed_texts_sync(texts=texts, model_id=os.environ.get("TPA_EMBEDDINGS_MODEL_ID"))
    if not embeddings:
        return 0

    tool_run_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO tool_runs (
          id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
          started_at, ended_at, confidence_hint, uncertainty_note
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
        """,
        (
            tool_run_id,
            ingest_batch_id,
            run_id,
            "embed_visual_assertions",
            json.dumps({"assertion_count": len(embeddings)}, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
            "running",
            _utc_now(),
            None,
            "medium",
            "Embedding visual assertions for retrieval.",
        ),
    )

    inserted = 0
    for (assertion_id, _), vec in zip(candidates, embeddings, strict=True):
        _db_execute(
            """
            INSERT INTO unit_embeddings (
              id, unit_type, unit_id, embedding, embedding_model_id, embedding_dim, created_at, tool_run_id, run_id
            )
            VALUES (%s, %s, %s::uuid, %s::vector, %s, %s, %s, %s::uuid, %s::uuid)
            ON CONFLICT (unit_type, unit_id, embedding_model_id) DO NOTHING
            """,
            (
                str(uuid4()),
                "visual_assertion",
                assertion_id,
                _vector_literal(vec),
                os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B"),
                len(vec) if isinstance(vec, list) else None,
                _utc_now(),
                tool_run_id,
                run_id,
            ),
        )
        inserted += 1

    _db_execute(
        """
        UPDATE tool_runs
        SET status = %s, outputs_logged = %s::jsonb, ended_at = %s
        WHERE id = %s::uuid
        """,
        (
            "success" if inserted > 0 else "error",
            json.dumps({"inserted": inserted}, ensure_ascii=False),
            _utc_now(),
            tool_run_id,
        ),
    )
    return inserted


def _embed_units(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    unit_type: str,
    rows: list[dict[str, Any]],
    text_key: str,
    id_key: str,
) -> int:
    candidates = [
        (r.get(id_key), r.get(text_key))
        for r in rows
        if isinstance(r.get(text_key), str) and r.get(text_key).strip() and r.get(id_key)
    ]
    if not candidates:
        return 0
    texts = [text for _, text in candidates]
    embeddings = _embed_texts_sync(texts=texts, model_id=os.environ.get("TPA_EMBEDDINGS_MODEL_ID"))
    if not embeddings:
        return 0
    tool_run_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO tool_runs (
          id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
          started_at, ended_at, confidence_hint, uncertainty_note
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
        """,
        (
            tool_run_id,
            ingest_batch_id,
            run_id,
            "embed_units",
            json.dumps({"unit_type": unit_type, "unit_count": len(embeddings)}, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
            "running",
            _utc_now(),
            None,
            "medium",
            "Embedding units for retrieval.",
        ),
    )
    inserted = 0
    for (unit_id, _), vec in zip(candidates, embeddings, strict=True):
        _db_execute(
            """
            INSERT INTO unit_embeddings (
              id, unit_type, unit_id, embedding, embedding_model_id, embedding_dim, created_at, tool_run_id, run_id
            )
            VALUES (%s, %s, %s::uuid, %s::vector, %s, %s, %s, %s::uuid, %s::uuid)
            ON CONFLICT (unit_type, unit_id, embedding_model_id) DO NOTHING
            """,
            (
                str(uuid4()),
                unit_type,
                unit_id,
                _vector_literal(vec),
                os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B"),
                len(vec) if isinstance(vec, list) else None,
                _utc_now(),
                tool_run_id,
                run_id,
            ),
        )
        inserted += 1
    _db_execute(
        """
        UPDATE tool_runs
        SET status = %s, outputs_logged = %s::jsonb, ended_at = %s
        WHERE id = %s::uuid
        """,
        (
            "success" if inserted > 0 else "error",
            json.dumps({"inserted": inserted, "unit_type": unit_type}, ensure_ascii=False),
            _utc_now(),
            tool_run_id,
        ),
    )
    return inserted


def _slice_blocks_for_llm(
    blocks: list[dict[str, Any]],
    *,
    max_chars: int = 12000,
    max_blocks: int = 140,
) -> list[list[dict[str, Any]]]:
    return [blocks]


def _build_sections_from_headings(
    *,
    policy_headings: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not policy_headings or not block_rows:
        return []
    block_order = [b for b in block_rows if b.get("block_id")]
    index_by_id = {b["block_id"]: idx for idx, b in enumerate(block_order)}
    block_ids_in_order = [b["block_id"] for b in block_order]
    block_lookup = {b.get("block_id"): b for b in block_order if b.get("block_id")}

    headings = [
        h
        for h in policy_headings
        if isinstance(h, dict) and isinstance(h.get("block_id"), str) and h.get("block_id") in index_by_id
    ]
    headings = sorted(headings, key=lambda h: index_by_id[h["block_id"]])
    if not headings:
        return []

    sections: list[dict[str, Any]] = []
    for idx, heading in enumerate(headings):
        heading_block_id = heading.get("block_id")
        if not isinstance(heading_block_id, str):
            continue
        start_idx = index_by_id[heading_block_id]
        end_idx = index_by_id[headings[idx + 1]["block_id"]] if idx + 1 < len(headings) else len(block_ids_in_order)
        section_block_ids = block_ids_in_order[start_idx:end_idx]
        heading_block = block_lookup.get(heading_block_id) or {}
        sections.append(
            {
                "section_id": f"docparse:{heading_block_id}",
                "policy_code": heading.get("policy_code"),
                "title": heading.get("policy_title"),
                "heading_text": heading_block.get("text"),
                "section_path": heading_block.get("section_path"),
                "block_ids": section_block_ids,
                "clauses": [],
                "definitions": [],
                "targets": [],
                "monitoring": [],
                "confidence_hint": heading.get("confidence_hint"),
                "uncertainty_note": heading.get("uncertainty_note"),
            }
        )
    return sections


def _llm_extract_policy_structure(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    document_id: str,
    document_title: str,
    blocks: list[dict[str, Any]],
    policy_headings: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    if not blocks:
        return [], [], ["no_blocks"]

    if policy_headings:
        sections = _build_sections_from_headings(policy_headings=policy_headings, block_rows=blocks)
        if not sections:
            return [], [], ["no_sections_from_headings"]

        prompt_id = "policy_clause_split_v1"
        system_template = (
            "You are a planning policy clause splitter. Return ONLY JSON with the following shape:\n"
            "{\n"
            '  "clauses": [\n'
            "    {\n"
            '      "clause_id": "string",\n'
            '      "clause_ref": "string|null",\n'
            '      "text": "string",\n'
            '      "block_ids": ["block_id", "..."],\n'
            '      "speech_act": {"normative_force": "...", "strength_hint": "...", "ambiguity_flags": [], "key_terms": [], "officer_interpretation_space": "...", "limitations_text": "..."},\n'
            '      "subject": "string|null",\n'
            '      "object": "string|null"\n'
            "    }\n"
            "  ],\n"
            '  "definitions": [\n'
            '    {"term": "string", "definition_text": "string", "block_ids": ["block_id", "..."]}\n'
            "  ],\n"
            '  "targets": [\n'
            '    {"metric": "string|null", "value": "number|null", "unit": "string|null", "timeframe": "string|null", "geography_ref": "string|null", "raw_text": "string", "block_ids": ["block_id", "..."]}\n'
            "  ],\n"
            '  "monitoring": [\n'
            '    {"indicator_text": "string", "block_ids": ["block_id", "..."]}\n'
            "  ],\n"
            '  "deliberate_omissions": [],\n'
            '  "limitations": []\n'
            "}\n"
            "Rules:\n"
            "- Use ONLY provided block_ids for evidence.\n"
            "- Do not invent clauses without block_ids.\n"
            "- If unsure, return empty lists and use unknown speech_act values.\n"
        )

        block_lookup = {b.get("block_id"): b for b in blocks if b.get("block_id")}
        tool_run_ids: list[str] = []
        errors: list[str] = []
        for section in sections:
            block_ids = section.get("block_ids") if isinstance(section.get("block_ids"), list) else []
            section_blocks = [
                {
                    "block_id": block_id,
                    "type": block_lookup.get(block_id, {}).get("type"),
                    "text": block_lookup.get(block_id, {}).get("text"),
                    "page_number": block_lookup.get(block_id, {}).get("page_number"),
                    "section_path": block_lookup.get(block_id, {}).get("section_path"),
                }
                for block_id in block_ids
                if block_lookup.get(block_id) and block_lookup.get(block_id).get("text")
            ]
            payload = {
                "document_id": document_id,
                "document_title": document_title,
                "policy_section": {
                    "section_id": section.get("section_id"),
                    "policy_code": section.get("policy_code"),
                    "title": section.get("title"),
                    "heading_text": section.get("heading_text"),
                    "section_path": section.get("section_path"),
                },
                "blocks": section_blocks,
            }
            obj, tool_run_id, errs = _llm_structured_sync(
                prompt_id=prompt_id,
                prompt_version=1,
                prompt_name="Policy clause splitter",
                purpose="Split policy section text into clauses and extract definitions, targets, and monitoring hooks.",
                system_template=system_template,
                user_payload=payload,
                time_budget_seconds=120.0,
                output_schema_ref="schemas/PolicySectionClauseParseResult.schema.json",
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
            )
            if tool_run_id:
                tool_run_ids.append(tool_run_id)
            errors.extend(errs)
            if not isinstance(obj, dict):
                continue
            for key in ("clauses", "definitions", "targets", "monitoring"):
                items = obj.get(key)
                if isinstance(items, list):
                    section[key] = [item for item in items if isinstance(item, dict)]
        return sections, tool_run_ids, errors

    prompt_id = "policy_structure_parse_v1"
    system_template = (
        "You are a planning policy parser. Return ONLY JSON with the following shape:\n"
        "{\n"
        '  "policy_sections": [\n'
        "    {\n"
        '      "section_id": "string",\n'
        '      "policy_code": "string|null",\n'
        '      "title": "string|null",\n'
        '      "heading_text": "string|null",\n'
        '      "section_path": "string|null",\n'
        '      "block_ids": ["block_id", "..."],\n'
        '      "clauses": [\n'
        "        {\n"
        '          "clause_id": "string",\n'
        '          "clause_ref": "string|null",\n'
        '          "text": "string",\n'
        '          "block_ids": ["block_id", "..."],\n'
        '          "speech_act": {"normative_force": "...", "strength_hint": "...", "ambiguity_flags": [], "key_terms": [], "officer_interpretation_space": "...", "limitations_text": "..."},\n'
        '          "subject": "string|null",\n'
        '          "object": "string|null"\n'
        "        }\n"
        "      ],\n"
        '      "definitions": [\n'
        '        {"term": "string", "definition_text": "string", "block_ids": ["block_id", "..."]}\n'
        "      ],\n"
        '      "targets": [\n'
        '        {"metric": "string|null", "value": "number|null", "unit": "string|null", "timeframe": "string|null", "geography_ref": "string|null", "raw_text": "string", "block_ids": ["block_id", "..."]}\n'
        "      ],\n"
        '      "monitoring": [\n'
        '        {"indicator_text": "string", "block_ids": ["block_id", "..."]}\n'
        "      ]\n"
        "    }\n"
        "  ],\n"
        '  "deliberate_omissions": [],\n'
        '  "limitations": []\n'
        "}\n"
        "Rules:\n"
        "- Use ONLY provided block_ids for evidence.\n"
        "- Do not invent clauses without block_ids.\n"
        "- If unsure, return empty lists and use unknown speech_act values.\n"
    )

    slices = _slice_blocks_for_llm(blocks)
    merged: dict[str, dict[str, Any]] = {}
    tool_run_ids: list[str] = []
    errors: list[str] = []

    for slice_blocks in slices:
        payload = {
            "document_id": document_id,
            "document_title": document_title,
            "blocks": [
                {
                    "block_id": b.get("block_id"),
                    "type": b.get("type"),
                    "text": b.get("text"),
                    "page_number": b.get("page_number"),
                    "section_path": b.get("section_path"),
                }
                for b in slice_blocks
                if b.get("block_id") and b.get("text")
            ],
        }
        obj, tool_run_id, errs = _llm_structured_sync(
            prompt_id=prompt_id,
            prompt_version=1,
            prompt_name="Policy structure parser",
            purpose="Extract policy sections, clauses, definitions, targets, and monitoring hooks from layout blocks.",
            system_template=system_template,
            user_payload=payload,
            time_budget_seconds=120.0,
            output_schema_ref="schemas/PolicyStructureParseResult.schema.json",
            ingest_batch_id=ingest_batch_id,
            run_id=run_id,
        )
        if tool_run_id:
            tool_run_ids.append(tool_run_id)
        errors.extend(errs)
        if not isinstance(obj, dict):
            continue
        sections = obj.get("policy_sections")
        if not isinstance(sections, list):
            continue
        for section in sections:
            if not isinstance(section, dict):
                continue
            block_ids = section.get("block_ids") if isinstance(section.get("block_ids"), list) else []
            block_ids = [b for b in block_ids if isinstance(b, str)]
            key = section.get("policy_code") or section.get("heading_text") or (block_ids[0] if block_ids else None)
            if not key:
                key = str(uuid4())
            existing = merged.get(str(key))
            if not existing:
                merged[str(key)] = {**section, "block_ids": block_ids}
                continue
            existing_blocks = existing.get("block_ids") if isinstance(existing.get("block_ids"), list) else []
            existing["block_ids"] = sorted(set(existing_blocks + block_ids))
            for list_key in ("clauses", "definitions", "targets", "monitoring"):
                incoming = section.get(list_key) if isinstance(section.get(list_key), list) else []
                if not incoming:
                    continue
                current = existing.get(list_key) if isinstance(existing.get(list_key), list) else []
                current.extend([item for item in incoming if isinstance(item, dict)])
                existing[list_key] = current

    return list(merged.values()), tool_run_ids, errors


def _confidence_hint_score(value: str | None) -> float:
    if not isinstance(value, str):
        return 0.0
    lowered = value.strip().lower()
    if lowered == "high":
        return 0.9
    if lowered == "medium":
        return 0.6
    if lowered == "low":
        return 0.3
    return 0.0


def _block_id_from_section_ref(section_ref: str | None) -> str | None:
    if not isinstance(section_ref, str) or not section_ref:
        return None
    if section_ref.startswith("p"):
        idx = 1
        while idx < len(section_ref) and section_ref[idx].isdigit():
            idx += 1
        if idx < len(section_ref) and section_ref[idx] == "-":
            return section_ref[idx + 1 :] or None
    return section_ref


def _persist_policy_logic_assets(
    *,
    document_id: str,
    run_id: str | None,
    sections: list[dict[str, Any]],
    policy_sections: list[dict[str, Any]],
    standard_matrices: list[dict[str, Any]],
    scope_candidates: list[dict[str, Any]],
    evidence_ref_map: dict[str, str],
    block_rows: list[dict[str, Any]],
) -> tuple[int, int]:
    section_by_source = {
        s.get("source_section_id"): s.get("policy_section_id")
        for s in policy_sections
        if s.get("source_section_id") and s.get("policy_section_id")
    }
    block_to_section: dict[str, str] = {}
    for section in sections:
        if not isinstance(section, dict):
            continue
        source_section_id = section.get("section_id")
        policy_section_id = section_by_source.get(source_section_id)
        if not policy_section_id:
            continue
        block_ids = section.get("block_ids") if isinstance(section.get("block_ids"), list) else []
        for block_id in block_ids:
            if isinstance(block_id, str):
                block_to_section[block_id] = policy_section_id

    matrix_count = 0
    for matrix in standard_matrices or []:
        if not isinstance(matrix, dict):
            continue
        evidence_ref = matrix.get("evidence_ref")
        section_ref = None
        if isinstance(evidence_ref, str):
            parsed = _parse_evidence_ref(evidence_ref)
            if parsed:
                section_ref = parsed[2]
        block_id = _block_id_from_section_ref(section_ref) if section_ref else None
        policy_section_id = block_to_section.get(block_id) if block_id else None
        evidence_ref_id = evidence_ref_map.get(section_ref) if section_ref else None
        matrix_id = str(uuid4())
        matrix_jsonb = {
            "matrix_id": matrix.get("matrix_id"),
            "inputs": matrix.get("inputs"),
            "outputs": matrix.get("outputs"),
            "logic_type": matrix.get("logic_type"),
            "evidence_ref": evidence_ref,
        }
        _db_execute(
            """
            INSERT INTO policy_matrices (
              id, document_id, policy_section_id, run_id, matrix_jsonb, evidence_ref_id, metadata_jsonb, created_at
            )
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s::jsonb, %s::uuid, %s::jsonb, %s)
            """,
            (
                matrix_id,
                document_id,
                policy_section_id,
                run_id,
                json.dumps(matrix_jsonb, ensure_ascii=False),
                evidence_ref_id,
                json.dumps({}, ensure_ascii=False),
                _utc_now(),
            ),
        )
        _ensure_kg_node(
            node_id=f"policy_matrix::{matrix_id}",
            node_type="PolicyMatrix",
            canonical_fk=matrix_id,
            props={"logic_type": matrix.get("logic_type"), "matrix_id": matrix.get("matrix_id")},
        )
        if policy_section_id:
            _insert_kg_edge(
                src_id=f"policy_section::{policy_section_id}",
                dst_id=f"policy_matrix::{matrix_id}",
                edge_type="CONTAINS_MATRIX",
                run_id=run_id,
                edge_class="docparse",
                resolve_method="docparse_standard_matrix",
                props={},
                evidence_ref_id=evidence_ref_id,
                tool_run_id=None,
            )
        matrix_count += 1

    scope_count = 0
    for scope in scope_candidates or []:
        if not isinstance(scope, dict):
            continue
        evidence_ref = scope.get("evidence_ref")
        section_ref = None
        if isinstance(evidence_ref, str):
            parsed = _parse_evidence_ref(evidence_ref)
            if parsed:
                section_ref = parsed[2]
        block_id = _block_id_from_section_ref(section_ref) if section_ref else None
        policy_section_id = block_to_section.get(block_id) if block_id else None
        evidence_ref_id = evidence_ref_map.get(section_ref) if section_ref else None
        scope_id = str(uuid4())
        scope_jsonb = {
            "scope_id": scope.get("id"),
            "geography_refs": scope.get("geography_refs"),
            "development_types": scope.get("development_types"),
            "use_classes": scope.get("use_classes"),
            "use_class_regime": scope.get("use_class_regime"),
            "temporal_scope": scope.get("temporal_scope"),
            "conditions": scope.get("conditions"),
            "evidence_ref": evidence_ref,
        }
        _db_execute(
            """
            INSERT INTO policy_scopes (
              id, document_id, policy_section_id, run_id, scope_jsonb, evidence_ref_id, metadata_jsonb, created_at
            )
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s::jsonb, %s::uuid, %s::jsonb, %s)
            """,
            (
                scope_id,
                document_id,
                policy_section_id,
                run_id,
                json.dumps(scope_jsonb, ensure_ascii=False),
                evidence_ref_id,
                json.dumps({}, ensure_ascii=False),
                _utc_now(),
            ),
        )
        _ensure_kg_node(
            node_id=f"policy_scope::{scope_id}",
            node_type="PolicyScope",
            canonical_fk=scope_id,
            props={},
        )
        if policy_section_id:
            _insert_kg_edge(
                src_id=f"policy_section::{policy_section_id}",
                dst_id=f"policy_scope::{scope_id}",
                edge_type="DEFINES_SCOPE",
                run_id=run_id,
                edge_class="docparse",
                resolve_method="docparse_scope_candidate",
                props={},
                evidence_ref_id=evidence_ref_id,
                tool_run_id=None,
            )
        scope_count += 1

    return matrix_count, scope_count


def _merge_policy_headings(
    *,
    sections: list[dict[str, Any]],
    policy_headings: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not policy_headings:
        return sections
    block_lookup = {b.get("block_id"): b for b in block_rows if b.get("block_id")}
    merged = [dict(s) for s in sections if isinstance(s, dict)]

    for heading in policy_headings:
        if not isinstance(heading, dict):
            continue
        block_id = heading.get("block_id")
        if not isinstance(block_id, str):
            continue
        policy_code = heading.get("policy_code")
        policy_title = heading.get("policy_title")
        heading_score = _confidence_hint_score(heading.get("confidence_hint"))

        matched = None
        for section in merged:
            block_ids = section.get("block_ids") if isinstance(section.get("block_ids"), list) else []
            if block_id in block_ids:
                matched = section
                break
        if not matched and isinstance(policy_code, str):
            for section in merged:
                if section.get("policy_code") == policy_code:
                    matched = section
                    break

        if matched:
            existing_score = _confidence_hint_score(matched.get("confidence_hint")) or 0.5
            if heading_score >= existing_score or not matched.get("policy_code"):
                if isinstance(policy_code, str) and policy_code.strip():
                    matched["policy_code"] = policy_code.strip()
                if isinstance(policy_title, str) and policy_title.strip():
                    matched["title"] = policy_title.strip()
                if not matched.get("heading_text"):
                    block = block_lookup.get(block_id) or {}
                    matched["heading_text"] = block.get("text")
            continue

        if heading_score >= 0.6:
            block = block_lookup.get(block_id) or {}
            merged.append(
                {
                    "section_id": f"docparse:{block_id}",
                    "policy_code": policy_code.strip() if isinstance(policy_code, str) else None,
                    "title": policy_title.strip() if isinstance(policy_title, str) else None,
                    "heading_text": block.get("text"),
                    "section_path": block.get("section_path"),
                    "block_ids": [block_id],
                    "clauses": [],
                    "definitions": [],
                    "targets": [],
                    "monitoring": [],
                    "confidence_hint": heading.get("confidence_hint"),
                    "uncertainty_note": heading.get("uncertainty_note"),
                }
            )

    return merged


def _infer_source_kind(filename: str | None, content_type: str | None) -> str:
    if isinstance(content_type, str):
        lowered = content_type.lower()
        if "pdf" in lowered:
            return "PDF"
        if "word" in lowered or "docx" in lowered:
            return "DOCX"
        if "html" in lowered:
            return "HTML"
        if "image" in lowered:
            return "IMAGE"
    if not isinstance(filename, str):
        return "OTHER"
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "PDF"
    if ext in {".doc", ".docx"}:
        return "DOCX"
    if ext in {".html", ".htm"}:
        return "HTML"
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        return "IMAGE"
    return "OTHER"


def _normalize_status_confidence(value: str | None) -> str:
    if not isinstance(value, str):
        return "LOW"
    upper = value.strip().upper()
    if upper in {"HIGH", "MEDIUM", "LOW"}:
        return upper
    return "LOW"


def _status_confidence_at_least(value: str, minimum: str) -> bool:
    order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    return order.get(value, 1) >= order.get(minimum, 2)


def _build_identity_evidence_options(
    *,
    document_id: str,
    block_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for block in block_rows:
        block_id = block.get("block_id")
        page_number = block.get("page_number")
        text = block.get("text")
        if not isinstance(block_id, str) or not isinstance(page_number, int):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        locator_value = f"p{page_number}-{block_id}"
        options.append(
            {
                "document_id": document_id,
                "locator_type": "paragraph",
                "locator_value": locator_value,
                "excerpt": text,
            }
        )
    return options


def _filter_identity_evidence(
    evidence: Any,
    *,
    document_id: str,
    options_by_key: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(evidence, list):
        return []
    filtered: list[dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        locator_type = item.get("locator_type")
        locator_value = item.get("locator_value")
        if not isinstance(locator_type, str) or not isinstance(locator_value, str):
            continue
        key = (locator_type, locator_value)
        option = options_by_key.get(key)
        if not option:
            continue
        filtered.append(
            {
                "document_id": document_id,
                "locator_type": locator_type,
                "locator_value": locator_value,
                "excerpt": option.get("excerpt") or "",
            }
        )
    return filtered


def _apply_document_weight_rules(
    *,
    identity: dict[str, Any],
    status: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    warnings: list[str] = []
    applied_rules: list[str] = []
    doc_family = identity.get("document_family") if isinstance(identity.get("document_family"), str) else "UNKNOWN"
    status_claim = status.get("status_claim") if isinstance(status.get("status_claim"), str) else "NOT_STATED"
    status_confidence = _normalize_status_confidence(status.get("status_confidence"))
    status_evidence = status.get("status_evidence") if isinstance(status.get("status_evidence"), list) else []
    status_evidence_missing = len(status_evidence) == 0
    status_claim_raw = status_claim

    if status_claim in {"ADOPTED", "MADE", "APPROVED"} and status_evidence_missing:
        status["status_claim"] = "NOT_STATED"
        status["status_confidence"] = "LOW"
        status["status_note"] = "Status claim lacked explicit evidence; downgraded to NOT_STATED."
        status_claim = "NOT_STATED"
        status_confidence = "LOW"
        warnings.append("NO_STATUS_EVIDENCE")
        applied_rules.append("R8_NO_EVIDENCE_DEGRADE")

    weight_class = "UNKNOWN"
    legal_assertion_level = "ASSERT_NONE"
    phrasing_guidance = "SAY_SYSTEM_CLASSIFIES_FOR_NAVIGATION_ONLY"
    basis: list[dict[str, Any]] = []

    if (
        doc_family in {"LOCAL_PLAN_DPD", "SPATIAL_DEVELOPMENT_STRATEGY", "NEIGHBOURHOOD_PLAN"}
        and status_claim in {"ADOPTED", "MADE", "APPROVED"}
        and _status_confidence_at_least(status_confidence, "MEDIUM")
        and not status_evidence_missing
    ):
        weight_class = "DEVELOPMENT_PLAN"
        legal_assertion_level = "ASSERT_CLAIMED_BY_DOCUMENT"
        phrasing_guidance = "SAY_DOCUMENT_PRESENTS_ITSELF_AS"
        applied_rules.append("R1_DEV_PLAN_EXPLICIT")
    elif (
        doc_family in {"LOCAL_PLAN_DPD", "SPATIAL_DEVELOPMENT_STRATEGY", "NEIGHBOURHOOD_PLAN"}
        and status_claim
        in {
            "REGULATION_18",
            "REGULATION_19",
            "PUBLICATION_DRAFT",
            "SUBMISSION",
            "EXAMINATION",
            "PROPOSED_MODIFICATIONS",
            "CONSULTATION_DRAFT",
        }
        and not status_evidence_missing
    ):
        weight_class = "EMERGING_POLICY"
        legal_assertion_level = "ASSERT_CLAIMED_BY_DOCUMENT"
        phrasing_guidance = "SAY_DOCUMENT_PRESENTS_ITSELF_AS"
        applied_rules.append("R2_EMERGING_POLICY_EXPLICIT")
    elif doc_family in {"SPD", "DESIGN_CODE"} and status_claim in {"ADOPTED", "APPROVED"} and not status_evidence_missing:
        weight_class = "SPD_GUIDANCE"
        legal_assertion_level = "ASSERT_CLAIMED_BY_DOCUMENT"
        phrasing_guidance = "SAY_DOCUMENT_PRESENTS_ITSELF_AS"
        applied_rules.append("R3_SPD_EXPLICIT")
    elif doc_family in {"NPPF_PPG_NATIONAL_POLICY"}:
        weight_class = "MATERIAL_CONSIDERATION"
        applied_rules.append("R4_NATIONAL_POLICY")
    elif doc_family
    in {
        "EVIDENCE_BASE",
        "TECHNICAL_REPORT",
        "CONSULTEE_RESPONSE",
        "PUBLIC_REPRESENTATION",
        "OFFICER_REPORT",
        "DECISION_NOTICE",
        "COMMITTEE_MINUTES",
        "APPEAL_DECISION",
        "S106_HEADS_OR_AGREEMENT",
        "APPLICANT_STATEMENT",
        "DRAWING_SET",
    }:
        weight_class = "MATERIAL_CONSIDERATION"
        applied_rules.append("R5_MATERIAL_CONSIDERATION_DEFAULT")
    elif doc_family in {"MARKETING_OR_ILLUSTRATIVE"}:
        weight_class = "ILLUSTRATIVE_LOW_WEIGHT"
        applied_rules.append("R6_ILLUSTRATIVE_LOW_WEIGHT")

    if weight_class == "UNKNOWN":
        plan_families = {"LOCAL_PLAN_DPD", "SPATIAL_DEVELOPMENT_STRATEGY", "NEIGHBOURHOOD_PLAN"}
        emerging_statuses = {
            "REGULATION_18",
            "REGULATION_19",
            "PUBLICATION_DRAFT",
            "SUBMISSION",
            "EXAMINATION",
            "PROPOSED_MODIFICATIONS",
            "CONSULTATION_DRAFT",
        }
        adopted_statuses = {"ADOPTED", "MADE", "APPROVED"}
        if doc_family in plan_families:
            if status_claim_raw in adopted_statuses:
                weight_class = "DEVELOPMENT_PLAN"
                applied_rules.append("R10_IMPLICIT_DEV_PLAN")
            elif status_claim_raw in emerging_statuses:
                weight_class = "EMERGING_POLICY"
                applied_rules.append("R11_IMPLICIT_EMERGING_POLICY")
            else:
                weight_class = "EMERGING_POLICY"
                applied_rules.append("R12_PLAN_FAMILY_ONLY")
            legal_assertion_level = "ASSERT_NONE"
            phrasing_guidance = "SAY_SYSTEM_CLASSIFIES_FOR_NAVIGATION_ONLY"
            if "LOW_PROVENANCE" not in warnings:
                warnings.append("LOW_PROVENANCE")
        elif doc_family in {"SPD", "DESIGN_CODE"}:
            weight_class = "SPD_GUIDANCE"
            applied_rules.append("R13_SPD_FAMILY_ONLY")
            legal_assertion_level = "ASSERT_NONE"
            phrasing_guidance = "SAY_SYSTEM_CLASSIFIES_FOR_NAVIGATION_ONLY"
            if "LOW_PROVENANCE" not in warnings:
                warnings.append("LOW_PROVENANCE")

    if status_claim in {"SUPERSEDED", "WITHDRAWN"}:
        warnings.append("TIME_SENSITIVE_STATUS")
        applied_rules.append("R7_SUPERSEDED_OR_WITHDRAWN_WARNING")

    basis_note: str | None = None
    basis_type: str | None = None
    if weight_class != "UNKNOWN" and applied_rules:
        last_rule = applied_rules[-1]
        if last_rule in {"R10_IMPLICIT_DEV_PLAN", "R11_IMPLICIT_EMERGING_POLICY"}:
            basis_type = "DERIVED_RULE"
            basis_note = "Status implied from document signals; explicit evidence missing."
        elif last_rule in {"R12_PLAN_FAMILY_ONLY", "R13_SPD_FAMILY_ONLY"}:
            basis_type = "DOCUMENT_FAMILY_ONLY"
            basis_note = "Document family indicates category; status not evidenced."

    if status_evidence and weight_class != "UNKNOWN":
        basis.append(
            {
                "basis_type": "EXPLICIT_IN_DOCUMENT",
                "evidence": status_evidence,
                "rule_id": applied_rules[-1] if applied_rules else None,
            }
        )
    elif basis_type:
        basis.append(
            {
                "basis_type": basis_type,
                "evidence": identity.get("identity_evidence") if isinstance(identity.get("identity_evidence"), list) else [],
                "rule_id": applied_rules[-1] if applied_rules else None,
                "note": basis_note,
            }
        )
    elif identity.get("identity_evidence"):
        basis.append(
            {
                "basis_type": "DOCUMENT_FAMILY_ONLY",
                "evidence": identity.get("identity_evidence"),
                "rule_id": applied_rules[-1] if applied_rules else None,
            }
        )

    weight = {
        "document_id": identity.get("document_id"),
        "weight_class": weight_class,
        "classification_basis": basis,
        "legal_assertion_level": legal_assertion_level,
        "phrasing_guidance": phrasing_guidance,
        "warnings": warnings,
    }
    return weight, status, applied_rules


def _extract_document_identity_status(
    *,
    ingest_batch_id: str | None,
    run_id: str | None,
    document_id: str,
    title: str,
    filename: str | None,
    content_type: str | None,
    block_rows: list[dict[str, Any]],
    evidence_ref_map: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    evidence_options = _build_identity_evidence_options(document_id=document_id, block_rows=block_rows)
    options_by_key = {
        (opt.get("locator_type"), opt.get("locator_value")): opt
        for opt in evidence_options
        if isinstance(opt.get("locator_type"), str) and isinstance(opt.get("locator_value"), str)
    }
    source_kind = _infer_source_kind(filename, content_type)
    system_template = (
        "You are a planning document classifier. Return ONLY valid JSON.\n"
        "Output shape:\n"
        "{\n"
        '  "identity": {\n'
        '    "document_id": "string",\n'
        '    "title": "string",\n'
        '    "author": "string",\n'
        '    "publisher": "string",\n'
        '    "jurisdiction": "UK-England|UK-Scotland|UK-Wales|UK-NI|Unknown",\n'
        '    "lpa_name": "string",\n'
        '    "lpa_code": "string",\n'
        '    "document_family": "LOCAL_PLAN_DPD|SPATIAL_DEVELOPMENT_STRATEGY|NEIGHBOURHOOD_PLAN|SPD|NPPF_PPG_NATIONAL_POLICY|EVIDENCE_BASE|TECHNICAL_REPORT|DESIGN_CODE|APPLICANT_STATEMENT|DRAWING_SET|CONSULTEE_RESPONSE|PUBLIC_REPRESENTATION|OFFICER_REPORT|DECISION_NOTICE|COMMITTEE_MINUTES|APPEAL_DECISION|S106_HEADS_OR_AGREEMENT|MARKETING_OR_ILLUSTRATIVE|UNKNOWN",\n'
        '    "source_kind": "PDF|DOCX|HTML|EMAIL|GIS|IMAGE|OTHER",\n'
        '    "version_label": "string",\n'
        '    "publication_date": "YYYY-MM-DD",\n'
        '    "revision_date": "YYYY-MM-DD",\n'
        '    "identity_evidence": [ {"document_id": "string", "locator_type": "paragraph", "locator_value": "string", "excerpt": "string"} ],\n'
        '    "notes": "string"\n'
        "  },\n"
        '  "status": {\n'
        '    "document_id": "string",\n'
        '    "status_claim": "ADOPTED|MADE|APPROVED|PUBLICATION_DRAFT|REGULATION_18|REGULATION_19|SUBMISSION|EXAMINATION|PROPOSED_MODIFICATIONS|CONSULTATION_DRAFT|WITHDRAWN|SUPERSEDED|NOT_STATED",\n'
        '    "status_confidence": "HIGH|MEDIUM|LOW",\n'
        '    "status_evidence": [ {"document_id": "string", "locator_type": "paragraph", "locator_value": "string", "excerpt": "string"} ],\n'
        '    "checked_at": "YYYY-MM-DDTHH:MM:SSZ",\n'
        '    "status_note": "string"\n'
        "  }\n"
        "}\n"
        "Rules:\n"
        "- Only use evidence refs from evidence_options.\n"
        "- Use locator_type \"paragraph\".\n"
        "- If status is not stated, set status_claim to NOT_STATED and status_confidence LOW.\n"
    )
    payload = {
        "document_id": document_id,
        "title": title,
        "source_kind_hint": source_kind,
        "evidence_options": evidence_options,
    }
    obj, tool_run_id, errs = _llm_structured_sync(
        prompt_id="document_identity_status_v1",
        prompt_version=1,
        prompt_name="Document identity/status classifier",
        purpose="Classify document identity, status, and planning weight with explicit evidence.",
        system_template=system_template,
        user_payload=payload,
        time_budget_seconds=120.0,
        output_schema_ref="schemas/DocumentIdentityStatusBundle.schema.json",
        ingest_batch_id=ingest_batch_id,
        run_id=run_id,
    )
    if not isinstance(obj, dict):
        return None, tool_run_id, errs

    identity = obj.get("identity") if isinstance(obj.get("identity"), dict) else {}
    status = obj.get("status") if isinstance(obj.get("status"), dict) else {}

    identity.setdefault("document_id", document_id)
    if not identity.get("title"):
        identity["title"] = title
    identity.setdefault("source_kind", source_kind)
    identity.setdefault("document_family", "UNKNOWN")
    identity.setdefault("jurisdiction", "Unknown")
    identity_evidence = _filter_identity_evidence(
        identity.get("identity_evidence"),
        document_id=document_id,
        options_by_key=options_by_key,
    )
    identity["identity_evidence"] = identity_evidence

    status.setdefault("document_id", document_id)
    status.setdefault("status_claim", "NOT_STATED")
    status["status_confidence"] = _normalize_status_confidence(status.get("status_confidence"))
    status_evidence = _filter_identity_evidence(
        status.get("status_evidence"),
        document_id=document_id,
        options_by_key=options_by_key,
    )
    status["status_evidence"] = status_evidence
    status["checked_at"] = _utc_now_iso()

    weight, status, rules_applied = _apply_document_weight_rules(identity=identity, status=status)
    bundle = {"identity": identity, "status": status, "weight": weight}

    identity_ref_ids: list[str] = []
    status_ref_ids: list[str] = []
    if evidence_ref_map:
        for ev in identity_evidence:
            locator_value = ev.get("locator_value")
            if isinstance(locator_value, str):
                ref_id = evidence_ref_map.get(locator_value)
                if ref_id:
                    identity_ref_ids.append(ref_id)
        for ev in status_evidence:
            locator_value = ev.get("locator_value")
            if isinstance(locator_value, str):
                ref_id = evidence_ref_map.get(locator_value)
                if ref_id:
                    status_ref_ids.append(ref_id)

    _db_execute(
        """
        INSERT INTO document_identity_status (
          id, document_id, run_id, identity_jsonb, status_jsonb, weight_jsonb, metadata_jsonb, tool_run_id, created_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::uuid, %s)
        """,
        (
            str(uuid4()),
            document_id,
            run_id,
            json.dumps(identity, ensure_ascii=False),
            json.dumps(status, ensure_ascii=False),
            json.dumps(weight, ensure_ascii=False),
            json.dumps(
                {
                    "rules_applied": rules_applied,
                    "identity_evidence_ref_ids": identity_ref_ids,
                    "status_evidence_ref_ids": status_ref_ids,
                },
                ensure_ascii=False,
            ),
            tool_run_id,
            _utc_now(),
        ),
    )
    _db_execute(
        """
        UPDATE documents
        SET document_status = %s,
            weight_hint = %s,
            metadata = metadata || %s::jsonb
        WHERE id = %s::uuid
        """,
        (
            status.get("status_claim"),
            weight.get("weight_class"),
            json.dumps(
                {
                    "document_family": identity.get("document_family"),
                    "status_confidence": status.get("status_confidence"),
                },
                ensure_ascii=False,
            ),
            document_id,
        ),
    )

    return bundle, tool_run_id, errs


def _ensure_kg_node(*, node_id: str, node_type: str, canonical_fk: str | None = None, props: dict[str, Any] | None = None) -> None:
    _db_execute(
        """
        INSERT INTO kg_node (node_id, node_type, props_jsonb, canonical_fk)
        VALUES (%s, %s, %s::jsonb, %s)
        ON CONFLICT (node_id) DO NOTHING
        """,
        (node_id, node_type, json.dumps(props or {}, ensure_ascii=False), canonical_fk),
    )


def _insert_kg_edge(
    *,
    src_id: str,
    dst_id: str,
    edge_type: str,
    run_id: str | None,
    edge_class: str | None = None,
    resolve_method: str | None = None,
    props: dict[str, Any] | None = None,
    evidence_ref_id: str | None = None,
    tool_run_id: str | None = None,
) -> None:
    _db_execute(
        """
        INSERT INTO kg_edge (
          edge_id, src_id, dst_id, edge_type, edge_class, resolve_method, props_jsonb,
          evidence_ref_id, tool_run_id, run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::uuid, %s::uuid, %s::uuid)
        """,
        (
            str(uuid4()),
            src_id,
            dst_id,
            edge_type,
            edge_class,
            resolve_method,
            json.dumps(props or {}, ensure_ascii=False),
            evidence_ref_id,
            tool_run_id,
            run_id,
        ),
    )


def _persist_policy_structure(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    sections: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    block_lookup = {b.get("block_id"): b for b in block_rows if b.get("block_id")}
    policy_sections: list[dict[str, Any]] = []
    policy_clauses: list[dict[str, Any]] = []
    definitions: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    monitoring: list[dict[str, Any]] = []

    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(uuid4())
        block_ids = section.get("block_ids") if isinstance(section.get("block_ids"), list) else []
        block_ids = [b for b in block_ids if isinstance(b, str)]
        block_texts = [block_lookup[b]["text"] for b in block_ids if b in block_lookup]
        section_text = "\n\n".join(block_texts).strip() if block_texts else str(section.get("text") or "").strip()
        if not section_text:
            continue
        page_numbers = [block_lookup[b]["page_number"] for b in block_ids if b in block_lookup]
        page_start = min(page_numbers) if page_numbers else None
        page_end = max(page_numbers) if page_numbers else None
        span_start = min([block_lookup[b]["span_start"] for b in block_ids if b in block_lookup and block_lookup[b].get("span_start") is not None], default=None)
        span_end = max([block_lookup[b]["span_end"] for b in block_ids if b in block_lookup and block_lookup[b].get("span_end") is not None], default=None)
        span_quality = "approx" if span_start is not None and span_end is not None else "none"
        evidence_ref_id = str(uuid4())

        metadata_jsonb = {
            "source_section_id": section.get("section_id"),
            "confidence_hint": section.get("confidence_hint"),
            "uncertainty_note": section.get("uncertainty_note"),
        }
        _db_execute(
            """
            INSERT INTO policy_sections (
              id, document_id, ingest_batch_id, run_id, source_artifact_id,
              policy_code, title, section_path, heading_text, text,
              page_start, page_end, span_start, span_end, span_quality,
              evidence_ref_id, metadata_jsonb
            )
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::uuid, %s::jsonb)
            """,
            (
                section_id,
                document_id,
                ingest_batch_id,
                run_id,
                source_artifact_id,
                section.get("policy_code"),
                section.get("title"),
                section.get("section_path"),
                section.get("heading_text"),
                section_text,
                page_start,
                page_end,
                span_start,
                span_end,
                span_quality,
                evidence_ref_id,
                json.dumps(metadata_jsonb, ensure_ascii=False),
            ),
        )
        _db_execute(
            "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
            (evidence_ref_id, "policy_section", section_id, section.get("policy_code") or section_id, run_id),
        )
        _ensure_kg_node(
            node_id=f"policy_section::{section_id}",
            node_type="PolicySection",
            canonical_fk=section_id,
            props={"policy_code": section.get("policy_code"), "title": section.get("title")},
        )
        policy_sections.append(
            {
                "policy_section_id": section_id,
                "source_section_id": section.get("section_id"),
                "policy_code": section.get("policy_code"),
                "title": section.get("title"),
                "section_path": section.get("section_path"),
                "text": section_text,
                "page_start": page_start,
                "page_end": page_end,
                "evidence_ref_id": evidence_ref_id,
                "block_ids": block_ids,
            }
        )

        clauses = section.get("clauses") if isinstance(section.get("clauses"), list) else []
        for clause in clauses:
            if not isinstance(clause, dict):
                continue
            clause_text = str(clause.get("text") or "").strip()
            clause_block_ids = clause.get("block_ids") if isinstance(clause.get("block_ids"), list) else []
            clause_block_ids = [b for b in clause_block_ids if isinstance(b, str)]
            if not clause_text and clause_block_ids:
                clause_text = "\n".join([block_lookup[b]["text"] for b in clause_block_ids if b in block_lookup]).strip()
            if not clause_text:
                continue
            clause_id = str(uuid4())
            clause_pages = [block_lookup[b]["page_number"] for b in clause_block_ids if b in block_lookup]
            clause_page = clause_pages[0] if clause_pages else None
            clause_span_start = min([block_lookup[b]["span_start"] for b in clause_block_ids if b in block_lookup and block_lookup[b].get("span_start") is not None], default=None)
            clause_span_end = max([block_lookup[b]["span_end"] for b in clause_block_ids if b in block_lookup and block_lookup[b].get("span_end") is not None], default=None)
            clause_span_quality = "approx" if clause_span_start is not None and clause_span_end is not None else "none"
            speech_act = _normalize_policy_speech_act(clause.get("speech_act"), tool_run_id=None, method="llm_policy_structure_v1")
            clause_evidence_ref_id = str(uuid4())
            _db_execute(
                """
                INSERT INTO policy_clauses (
                  id, policy_section_id, run_id, clause_ref, text, page_number,
                  span_start, span_end, span_quality, speech_act_jsonb, conditions_jsonb,
                  subject, object, evidence_ref_id, source_artifact_id, metadata_jsonb
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s::uuid, %s::uuid, %s::jsonb)
                """,
                (
                    clause_id,
                    section_id,
                    run_id,
                    clause.get("clause_ref"),
                    clause_text,
                    clause_page,
                    clause_span_start,
                    clause_span_end,
                    clause_span_quality,
                    json.dumps(speech_act, ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    clause.get("subject"),
                    clause.get("object"),
                    clause_evidence_ref_id,
                    source_artifact_id,
                    json.dumps({"block_ids": clause_block_ids}, ensure_ascii=False),
                ),
            )
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (clause_evidence_ref_id, "policy_clause", clause_id, clause.get("clause_ref") or clause_id, run_id),
            )
            clause_evidence_ref = f"policy_clause::{clause_id}::{clause.get('clause_ref') or clause_id}"
            _ensure_kg_node(
                node_id=f"policy_clause::{clause_id}",
                node_type="PolicyClause",
                canonical_fk=clause_id,
                props={"policy_section_id": section_id, "clause_ref": clause.get("clause_ref")},
            )
            policy_clauses.append(
                {
                    "policy_clause_id": clause_id,
                    "policy_section_id": section_id,
                    "policy_code": section.get("policy_code"),
                    "text": clause_text,
                    "evidence_ref_id": clause_evidence_ref_id,
                    "evidence_ref": clause_evidence_ref,
                    "block_ids": clause_block_ids,
                }
            )

        for definition in section.get("definitions") if isinstance(section.get("definitions"), list) else []:
            if not isinstance(definition, dict):
                continue
            term = definition.get("term")
            definition_text = definition.get("definition_text")
            if not isinstance(term, str) or not isinstance(definition_text, str):
                continue
            definition_id = str(uuid4())
            def_evidence_ref_id = str(uuid4())
            _db_execute(
                """
                INSERT INTO policy_definitions (
                  id, policy_section_id, run_id, term, definition_text, evidence_ref_id, source_artifact_id, metadata_jsonb
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s::uuid, %s::uuid, %s::jsonb)
                """,
                (
                    definition_id,
                    section_id,
                    run_id,
                    term,
                    definition_text,
                    def_evidence_ref_id,
                    source_artifact_id,
                    json.dumps({}, ensure_ascii=False),
                ),
            )
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (def_evidence_ref_id, "policy_definition", definition_id, term, run_id),
            )
            definitions.append(
                {
                    "definition_id": definition_id,
                    "policy_section_id": section_id,
                    "term": term,
                    "evidence_ref_id": def_evidence_ref_id,
                }
            )

        for target in section.get("targets") if isinstance(section.get("targets"), list) else []:
            if not isinstance(target, dict):
                continue
            target_id = str(uuid4())
            target_evidence_ref_id = str(uuid4())
            _db_execute(
                """
                INSERT INTO policy_targets (
                  id, policy_section_id, run_id, metric, value, unit, timeframe, geography_ref, raw_text,
                  evidence_ref_id, source_artifact_id, metadata_jsonb
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s::uuid, %s::uuid, %s::jsonb)
                """,
                (
                    target_id,
                    section_id,
                    run_id,
                    target.get("metric"),
                    target.get("value"),
                    target.get("unit"),
                    target.get("timeframe"),
                    target.get("geography_ref"),
                    target.get("raw_text"),
                    target_evidence_ref_id,
                    source_artifact_id,
                    json.dumps({}, ensure_ascii=False),
                ),
            )
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (target_evidence_ref_id, "policy_target", target_id, "target", run_id),
            )
            targets.append(
                {
                    "target_id": target_id,
                    "policy_section_id": section_id,
                    "evidence_ref_id": target_evidence_ref_id,
                }
            )

        for hook in section.get("monitoring") if isinstance(section.get("monitoring"), list) else []:
            if not isinstance(hook, dict):
                continue
            indicator = hook.get("indicator_text")
            if not isinstance(indicator, str) or not indicator.strip():
                continue
            hook_id = str(uuid4())
            hook_evidence_ref_id = str(uuid4())
            _db_execute(
                """
                INSERT INTO policy_monitoring_hooks (
                  id, policy_section_id, run_id, indicator_text, evidence_ref_id, source_artifact_id, metadata_jsonb
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s::uuid, %s::uuid, %s::jsonb)
                """,
                (
                    hook_id,
                    section_id,
                    run_id,
                    indicator,
                    hook_evidence_ref_id,
                    source_artifact_id,
                    json.dumps({}, ensure_ascii=False),
                ),
            )
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (hook_evidence_ref_id, "policy_monitoring_hook", hook_id, "monitoring", run_id),
            )
            monitoring.append(
                {
                    "monitoring_hook_id": hook_id,
                    "policy_section_id": section_id,
                    "indicator_text": indicator,
                    "evidence_ref_id": hook_evidence_ref_id,
                }
            )

    return policy_sections, policy_clauses, definitions, targets, monitoring


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:80] or "mention"


def _llm_extract_edges(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    policy_clauses: list[dict[str, Any]],
    policy_codes: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    if not policy_clauses:
        return [], [], [], [], ["no_clauses"]
    prompt_id = "policy_edge_parse_v1"
    system_template = (
        "You are extracting citations and mentions from planning policy clauses.\n"
        "Return ONLY JSON with shape:\n"
        "{\n"
        '  "citations": [\n'
        '    {"source_clause_id": "uuid", "target_policy_code": "string", "confidence": "low|medium|high"}\n'
        "  ],\n"
        '  "mentions": [\n'
        '    {"source_clause_id": "uuid", "mention_text": "string", "mention_kind": "place|constraint|designation|policy_ref|defined_term|metric|other", "confidence": "low|medium|high"}\n'
        "  ],\n"
        '  "conditions": [\n'
        '    {"source_clause_id": "uuid", "trigger_text": "string", "operator": "EXCEPTION|QUALIFICATION|DEPENDENCY|DISCRETION_GATE|PRIORITY_OVERRIDE", "testable": true, "requires": [], "severity": "hard|soft|discretionary", "test_type": "binary|graded|narrative", "confidence": "low|medium|high"}\n'
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Only cite policy codes that appear in the provided policy_codes list.\n"
        "- Use mention_kind based on context; do not invent entities.\n"
        "- Conditions must quote the trigger text (unless/subject to/where appropriate).\n"
    )

    tool_run_ids: list[str] = []
    errors: list[str] = []
    citations: list[dict[str, Any]] = []
    mentions: list[dict[str, Any]] = []
    conditions: list[dict[str, Any]] = []

    batch_size = 30
    for i in range(0, len(policy_clauses), batch_size):
        batch = policy_clauses[i : i + batch_size]
        payload = {
            "policy_codes": policy_codes,
            "clauses": [{"policy_clause_id": c.get("policy_clause_id"), "text": c.get("text")} for c in batch],
        }
        obj, tool_run_id, errs = _llm_structured_sync(
            prompt_id=prompt_id,
            prompt_version=1,
            prompt_name="Policy edge parser",
            purpose="Extract policy citations, clause mentions, and clause conditions from clauses.",
            system_template=system_template,
            user_payload=payload,
            time_budget_seconds=90.0,
            output_schema_ref="schemas/PolicyEdgeParseResult.schema.json",
            ingest_batch_id=ingest_batch_id,
            run_id=run_id,
        )
        if tool_run_id:
            tool_run_ids.append(tool_run_id)
        errors.extend(errs)
        if not isinstance(obj, dict):
            continue
        if isinstance(obj.get("citations"), list):
            citations.extend([c for c in obj["citations"] if isinstance(c, dict)])
        if isinstance(obj.get("mentions"), list):
            mentions.extend([m for m in obj["mentions"] if isinstance(m, dict)])
        if isinstance(obj.get("conditions"), list):
            conditions.extend([c for c in obj["conditions"] if isinstance(c, dict)])

    return citations, mentions, conditions, tool_run_ids, errors


def _persist_policy_edges(
    *,
    policy_sections: list[dict[str, Any]],
    policy_clauses: list[dict[str, Any]],
    definitions: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    monitoring: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    mentions: list[dict[str, Any]],
    conditions: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
    tool_run_ids: list[str],
    run_id: str | None,
) -> None:
    section_by_code = {
        s.get("policy_code"): s.get("policy_section_id")
        for s in policy_sections
        if s.get("policy_code") and s.get("policy_section_id")
    }
    clause_ref_map = {c.get("policy_clause_id"): c for c in policy_clauses if c.get("policy_clause_id")}
    block_lookup = {b.get("block_id"): b for b in block_rows if b.get("block_id")}
    tool_run_id = tool_run_ids[0] if tool_run_ids else None

    for definition in definitions:
        definition_id = definition.get("definition_id")
        section_id = definition.get("policy_section_id")
        if not definition_id or not section_id:
            continue
        _insert_kg_edge(
            src_id=f"policy_section::{section_id}",
            dst_id=f"definition::{definition_id}",
            edge_type="DEFINES",
            run_id=run_id,
            edge_class="llm",
            resolve_method="llm_policy_structure_v1",
            props={"term": definition.get("term")},
            evidence_ref_id=definition.get("evidence_ref_id"),
            tool_run_id=tool_run_id,
        )

    for target in targets:
        target_id = target.get("target_id")
        section_id = target.get("policy_section_id")
        if not target_id or not section_id:
            continue
        _insert_kg_edge(
            src_id=f"policy_section::{section_id}",
            dst_id=f"target::{target_id}",
            edge_type="TARGET_OF",
            run_id=run_id,
            edge_class="llm",
            resolve_method="llm_policy_structure_v1",
            props={},
            evidence_ref_id=target.get("evidence_ref_id"),
            tool_run_id=tool_run_id,
        )

    for hook in monitoring:
        hook_id = hook.get("monitoring_hook_id")
        section_id = hook.get("policy_section_id")
        if not hook_id or not section_id:
            continue
        _insert_kg_edge(
            src_id=f"policy_section::{section_id}",
            dst_id=f"monitoring::{hook_id}",
            edge_type="MONITORS",
            run_id=run_id,
            edge_class="llm",
            resolve_method="llm_policy_structure_v1",
            props={},
            evidence_ref_id=hook.get("evidence_ref_id"),
            tool_run_id=tool_run_id,
        )

    for cite in citations:
        source_clause_id = cite.get("source_clause_id")
        target_code = cite.get("target_policy_code")
        if not source_clause_id or not target_code:
            continue
        src = clause_ref_map.get(source_clause_id)
        dst_section_id = section_by_code.get(target_code)
        if dst_section_id:
            dst_id = f"policy_section::{dst_section_id}"
        else:
            dst_id = f"policy_ref::{_slugify(str(target_code))}"
            _ensure_kg_node(node_id=dst_id, node_type="PolicyRef", canonical_fk=None, props={"policy_code": target_code})
        _insert_kg_edge(
            src_id=f"policy_clause::{source_clause_id}",
            dst_id=dst_id,
            edge_type="CITES",
            run_id=run_id,
            edge_class="llm",
            resolve_method="llm_policy_edge_parse_v1",
            props={"confidence": cite.get("confidence")},
            evidence_ref_id=src.get("evidence_ref_id") if src else None,
            tool_run_id=tool_run_id,
        )

    if mentions:
        _persist_policy_clause_mentions(
            mentions=mentions,
            clause_ref_map=clause_ref_map,
            tool_run_id=tool_run_id,
            run_id=run_id,
        )

    if conditions:
        _apply_clause_conditions(
            conditions=conditions,
            clause_ref_map=clause_ref_map,
            block_lookup=block_lookup,
            run_id=run_id,
        )


def _persist_policy_clause_mentions(
    *,
    mentions: list[dict[str, Any]],
    clause_ref_map: dict[str, dict[str, Any]],
    tool_run_id: str | None,
    run_id: str | None,
) -> None:
    for mention in mentions:
        source_clause_id = mention.get("source_clause_id")
        mention_text = mention.get("mention_text")
        mention_kind = mention.get("mention_kind")
        if not source_clause_id or not mention_text or not mention_kind:
            continue
        clause = clause_ref_map.get(source_clause_id)
        evidence_ref_id = clause.get("evidence_ref_id") if clause else None
        _db_execute(
            """
            INSERT INTO policy_clause_mentions (
              id, policy_clause_id, run_id, mention_text, mention_kind, evidence_refs_jsonb,
              resolved_entity_type, resolved_entity_id, resolution_confidence, tool_run_id, metadata_jsonb, created_at
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s, %s, %s, %s::uuid, %s::jsonb, %s)
            """,
            (
                str(uuid4()),
                source_clause_id,
                run_id,
                mention_text,
                mention_kind,
                json.dumps([evidence_ref_id] if evidence_ref_id else [], ensure_ascii=False),
                None,
                None,
                None,
                tool_run_id,
                json.dumps({"confidence": mention.get("confidence")}, ensure_ascii=False),
                _utc_now(),
            ),
        )


def _apply_clause_conditions(
    *,
    conditions: list[dict[str, Any]],
    clause_ref_map: dict[str, dict[str, Any]],
    block_lookup: dict[str, dict[str, Any]],
    run_id: str | None,
) -> None:
    by_clause: dict[str, list[dict[str, Any]]] = {}
    allowed_ops = {"EXCEPTION", "QUALIFICATION", "DEPENDENCY", "DISCRETION_GATE", "PRIORITY_OVERRIDE"}
    allowed_severity = {"hard", "soft", "discretionary"}
    allowed_test_type = {"binary", "graded", "narrative"}
    for cond in conditions:
        source_clause_id = cond.get("source_clause_id")
        trigger_text = cond.get("trigger_text")
        operator = cond.get("operator")
        if not source_clause_id or not trigger_text or not operator:
            continue
        if operator not in allowed_ops:
            continue
        clause = clause_ref_map.get(source_clause_id)
        evidence_ref = clause.get("evidence_ref") if clause else None
        clause_block_ids = clause.get("block_ids") if isinstance(clause.get("block_ids"), list) else []
        clause_block_ids = [b for b in clause_block_ids if isinstance(b, str)]
        span_refs: list[str] = []
        trigger_spans: list[dict[str, Any]] = []
        for block_id in clause_block_ids:
            block = block_lookup.get(block_id)
            if not block:
                continue
            block_text = str(block.get("text") or "")
            spans = _find_trigger_spans(block_text, str(trigger_text))
            if not spans:
                continue
            block_evidence_ref = block.get("evidence_ref")
            if block_evidence_ref and isinstance(block_evidence_ref, str):
                span_refs.append(block_evidence_ref)
            for span in spans:
                trigger_spans.append(
                    {
                        "block_id": block_id,
                        "span_start": span.get("start"),
                        "span_end": span.get("end"),
                        "span_quality": span.get("quality"),
                        "evidence_ref": block_evidence_ref,
                    }
                )
        if not span_refs and evidence_ref and isinstance(evidence_ref, str):
            span_refs = [evidence_ref]
        cond_key = f"{source_clause_id}|{operator}|{trigger_text}"
        condition_id = hashlib.sha1(cond_key.encode("utf-8")).hexdigest()
        item = {
            "condition_id": condition_id,
            "operator": operator,
            "trigger_text": trigger_text,
            "testable": bool(cond.get("testable")),
            "requires": cond.get("requires") if isinstance(cond.get("requires"), list) else [],
            "severity": cond.get("severity") if cond.get("severity") in allowed_severity else None,
            "test_type": cond.get("test_type") if cond.get("test_type") in allowed_test_type else None,
            "span_evidence_refs": span_refs,
            "trigger_spans": trigger_spans,
        }
        by_clause.setdefault(source_clause_id, []).append(item)

    for clause_id, items in by_clause.items():
        _db_execute(
            """
            UPDATE policy_clauses
            SET conditions_jsonb = %s::jsonb
            WHERE id = %s::uuid
            """,
            (json.dumps(items, ensure_ascii=False), clause_id),
        )


def _persist_kg_nodes(
    *,
    document_id: str,
    chunks: list[dict[str, Any]],
    visual_assets: list[dict[str, Any]],
    policy_sections: list[dict[str, Any]] | None = None,
    policy_clauses: list[dict[str, Any]] | None = None,
    definitions: list[dict[str, Any]] | None = None,
    targets: list[dict[str, Any]] | None = None,
    monitoring: list[dict[str, Any]] | None = None,
) -> None:
    _db_execute(
        "INSERT INTO kg_node (node_id, node_type, props_jsonb, canonical_fk) VALUES (%s, %s, %s::jsonb, %s)",
        (f"doc::{document_id}", "Document", json.dumps({}, ensure_ascii=False), document_id),
    )
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        if not chunk_id:
            continue
        _db_execute(
            "INSERT INTO kg_node (node_id, node_type, props_jsonb, canonical_fk) VALUES (%s, %s, %s::jsonb, %s)",
            (f"chunk::{chunk_id}", "Chunk", json.dumps({}, ensure_ascii=False), chunk_id),
        )
    for asset in visual_assets:
        asset_id = asset.get("visual_asset_id")
        if not asset_id:
            continue
        _db_execute(
            "INSERT INTO kg_node (node_id, node_type, props_jsonb, canonical_fk) VALUES (%s, %s, %s::jsonb, %s)",
            (f"visual_asset::{asset_id}", "VisualAsset", json.dumps(asset.get("metadata") or {}, ensure_ascii=False), asset_id),
        )

    for section in policy_sections or []:
        section_id = section.get("policy_section_id")
        if not section_id:
            continue
        _ensure_kg_node(
            node_id=f"policy_section::{section_id}",
            node_type="PolicySection",
            canonical_fk=str(section_id),
            props={"policy_code": section.get("policy_code"), "title": section.get("title")},
        )

    for clause in policy_clauses or []:
        clause_id = clause.get("policy_clause_id")
        if not clause_id:
            continue
        _ensure_kg_node(
            node_id=f"policy_clause::{clause_id}",
            node_type="PolicyClause",
            canonical_fk=str(clause_id),
            props={"policy_section_id": clause.get("policy_section_id"), "policy_code": clause.get("policy_code")},
        )

    for definition in definitions or []:
        definition_id = definition.get("definition_id")
        if not definition_id:
            continue
        _ensure_kg_node(
            node_id=f"definition::{definition_id}",
            node_type="Definition",
            canonical_fk=str(definition_id),
            props={"term": definition.get("term")},
        )

    for target in targets or []:
        target_id = target.get("target_id")
        if not target_id:
            continue
        _ensure_kg_node(
            node_id=f"target::{target_id}",
            node_type="Target",
            canonical_fk=str(target_id),
            props={},
        )

    for hook in monitoring or []:
        hook_id = hook.get("monitoring_hook_id")
        if not hook_id:
            continue
        _ensure_kg_node(
            node_id=f"monitoring::{hook_id}",
            node_type="MonitoringHook",
            canonical_fk=str(hook_id),
            props={"indicator_text": hook.get("indicator_text")},
        )


def _update_document_semantic_metadata(*, document_id: str, semantic: dict[str, Any]) -> None:
    if not semantic:
        return
    payload: dict[str, Any] = {}
    for key in ("policy_headings", "standard_matrices", "scope_candidates"):
        items = semantic.get(key) if isinstance(semantic.get(key), list) else []
        if items:
            payload[key] = items
    if not payload:
        return
    _db_execute(
        "UPDATE documents SET metadata = metadata || %s::jsonb WHERE id = %s::uuid",
        (json.dumps(payload, ensure_ascii=False), document_id),
    )


@celery_app.task(name="tpa_api.ingest_worker.process_ingest_job")
def process_ingest_job(ingest_job_id: str) -> dict[str, Any]:
    init_db_pool()
    try:
        job = _db_fetch_one(
            """
            SELECT id, ingest_batch_id, authority_id, plan_cycle_id, job_type, inputs_jsonb, status
            FROM ingest_jobs
            WHERE id = %s::uuid
            """,
            (ingest_job_id,),
        )
        if not job:
            return {"status": "missing"}
        if job.get("status") == "running":
            return {"status": "already_running"}

        started = _utc_now()
        _update_job_status(ingest_job_id=ingest_job_id, status="running", started_at=started)

        authority_id = job.get("authority_id")
        plan_cycle_id = str(job.get("plan_cycle_id")) if job.get("plan_cycle_id") else None
        ingest_batch_id = str(job.get("ingest_batch_id")) if job.get("ingest_batch_id") else None
        inputs = job.get("inputs_jsonb") if isinstance(job.get("inputs_jsonb"), dict) else {}

        documents = inputs.get("documents") if isinstance(inputs.get("documents"), list) else []
        pack_dir = inputs.get("pack_dir") if isinstance(inputs.get("pack_dir"), str) else None
        if not documents:
            pack_dir = pack_dir or str(_authority_packs_root() / authority_id)
            manifest = _load_authority_pack_manifest(authority_id)
            documents = _normalize_authority_pack_documents(manifest)

        run_id: str | None = None
        if ingest_batch_id:
            run_id = _create_ingest_run(
                ingest_batch_id=ingest_batch_id,
                authority_id=authority_id,
                plan_cycle_id=plan_cycle_id,
                inputs={
                    "job_type": job.get("job_type"),
                    "document_count": len(documents),
                    "authority_id": authority_id,
                    "plan_cycle_id": plan_cycle_id,
                },
            )

        counts = {
            "documents_seen": 0,
            "document_identity_status": 0,
            "pages": 0,
            "layout_blocks": 0,
            "tables": 0,
            "vector_paths": 0,
            "chunks": 0,
            "visual_assets": 0,
            "segmentation_masks": 0,
            "visual_asset_regions": 0,
            "visual_asset_links": 0,
            "visual_semantic_assets": 0,
            "visual_semantic_assertions": 0,
            "visual_semantic_agents": 0,
            "georef_attempts": 0,
            "georef_success": 0,
            "transforms": 0,
            "projection_artifacts": 0,
            "policy_sections": 0,
            "policy_clauses": 0,
            "definitions": 0,
            "targets": 0,
            "monitoring": 0,
            "unit_embeddings_chunk": 0,
            "unit_embeddings_policy_section": 0,
            "unit_embeddings_policy_clause": 0,
            "unit_embeddings_visual": 0,
            "unit_embeddings_visual_assertion": 0,
        }
        errors: list[str] = []
        step_counts: dict[str, int] = {}

        if ingest_batch_id:
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="anchor_raw",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="docling_parse",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="canonical_load",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="document_identity_status",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="visual_semantics_asset",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="visual_segmentation",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="visual_semantics_regions",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="visual_georef",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="visual_linking",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="visual_embeddings",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="visual_assertion_embeddings",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="structural_llm",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="edges_llm",
                inputs={"document_count": len(documents)},
            )
            _start_run_step(
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
                step_name="embeddings",
                inputs={"document_count": len(documents)},
            )

        minio_client = minio_client_or_none()
        bucket = os.environ.get("TPA_S3_BUCKET")

        for doc in documents:
            counts["documents_seen"] += 1
            rel_path = doc.get("file_path")
            source_url = doc.get("source_url") or doc.get("url")
            if not source_url and _is_http_url(rel_path):
                source_url = str(rel_path)
                rel_path = None

            data_bytes: bytes | None = None
            filename = None
            content_type = None
            if source_url:
                result = _web_automation_ingest_url(
                    url=source_url,
                    ingest_batch_id=ingest_batch_id or str(uuid4()),
                    run_id=run_id,
                )
                if not result.get("ok"):
                    errors.append(f"web_ingest_failed:{source_url}")
                    continue
                data_bytes = result.get("bytes")
                content_type = result.get("content_type") or "application/pdf"
                filename = result.get("filename") or _derive_filename_for_url(source_url, content_type=content_type)
            if data_bytes is None and rel_path:
                pack_path = Path(pack_dir or "") / str(rel_path)
                if not pack_path.exists():
                    errors.append(f"missing_file:{pack_path}")
                    continue
                data_bytes = pack_path.read_bytes()
                filename = pack_path.name
                content_type = mimetypes.guess_type(pack_path.name)[0] or "application/pdf"

            if data_bytes is None:
                errors.append("missing_document_bytes")
                continue

            filename = filename or "document.pdf"
            raw_source_uri = source_url or (str(rel_path) if rel_path else filename)
            raw_blob_path, raw_sha256 = _store_raw_blob(
                client=minio_client,
                bucket=bucket,
                authority_id=authority_id,
                filename=filename,
                data=data_bytes,
            )
            raw_artifact_id = _ensure_artifact(artifact_type="raw_pdf", path=raw_blob_path)
            doc_metadata = {
                "title": doc.get("title") or filename,
                "source_url": source_url,
                "document_type": doc.get("document_type"),
            }
            document_id = _ensure_document_row(
                authority_id=authority_id,
                plan_cycle_id=plan_cycle_id,
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                blob_path=raw_blob_path,
                metadata=doc_metadata,
                raw_blob_path=raw_blob_path,
                raw_sha256=raw_sha256,
                raw_bytes=len(data_bytes),
                raw_content_type=content_type,
                raw_source_uri=raw_source_uri,
                raw_artifact_id=raw_artifact_id,
            )
            step_counts["anchor_raw"] = step_counts.get("anchor_raw", 0) + 1

            parse_result = _call_docparse_bundle(
                file_bytes=data_bytes,
                filename=filename,
                metadata={
                    "authority_id": authority_id,
                    "plan_cycle_id": plan_cycle_id,
                    "document_id": document_id,
                    "job_id": ingest_job_id,
                    "source_url": source_url,
                },
            )
            bundle_path = parse_result.get("parse_bundle_path")
            if not isinstance(bundle_path, str):
                errors.append("parse_bundle_missing")
                continue
            step_counts["docling_parse"] = step_counts.get("docling_parse", 0) + 1

            bundle = _load_parse_bundle(bundle_path)
            _insert_parse_bundle_record(
                ingest_job_id=ingest_job_id,
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                document_id=document_id,
                schema_version=bundle.get("schema_version") or "2.0",
                blob_path=bundle_path,
                metadata={
                    "tables_unimplemented": bool(bundle.get("tables_unimplemented")),
                    "parse_flags": bundle.get("parse_flags") if isinstance(bundle.get("parse_flags"), list) else [],
                    "tool_run_count": len(bundle.get("tool_runs") or []),
                },
            )

            tool_runs = bundle.get("tool_runs") if isinstance(bundle.get("tool_runs"), list) else []
            _persist_tool_runs(ingest_batch_id=ingest_batch_id, run_id=run_id, tool_runs=tool_runs)

            pages = bundle.get("pages") if isinstance(bundle.get("pages"), list) else []
            _persist_pages(
                document_id=document_id,
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                source_artifact_id=raw_artifact_id,
                pages=pages,
            )
            counts["pages"] += len(pages)

            bundle_evidence_refs = bundle.get("evidence_refs") if isinstance(bundle.get("evidence_refs"), list) else []
            evidence_ref_map = _persist_bundle_evidence_refs(run_id=run_id, evidence_refs=bundle_evidence_refs)

            blocks = bundle.get("layout_blocks") if isinstance(bundle.get("layout_blocks"), list) else []
            block_rows = _persist_layout_blocks(
                document_id=document_id,
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                source_artifact_id=raw_artifact_id,
                pages=pages,
                blocks=blocks,
                evidence_ref_map=evidence_ref_map,
            )
            counts["layout_blocks"] += len(block_rows)

            tables = bundle.get("tables") if isinstance(bundle.get("tables"), list) else []
            _persist_document_tables(
                document_id=document_id,
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                source_artifact_id=raw_artifact_id,
                tables=tables,
            )
            counts["tables"] += len(tables)

            vector_paths = bundle.get("vector_paths") if isinstance(bundle.get("vector_paths"), list) else []
            _persist_vector_paths(
                document_id=document_id,
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                source_artifact_id=raw_artifact_id,
                vector_paths=vector_paths,
            )
            counts["vector_paths"] += len(vector_paths)

            chunk_rows = _persist_chunks_from_blocks(
                document_id=document_id,
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                source_artifact_id=raw_artifact_id,
                block_rows=block_rows,
            )
            counts["chunks"] += len(chunk_rows)

            visual_assets = bundle.get("visual_assets") if isinstance(bundle.get("visual_assets"), list) else []
            visual_rows = _persist_visual_assets(
                document_id=document_id,
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                source_artifact_id=raw_artifact_id,
                visual_assets=visual_assets,
                evidence_ref_map=evidence_ref_map,
            )
            counts["visual_assets"] += len(visual_rows)
            _persist_visual_features(visual_assets=visual_rows, run_id=run_id)

            semantic = bundle.get("semantic") if isinstance(bundle.get("semantic"), dict) else {}
            _persist_visual_semantic_features(visual_assets=visual_rows, semantic=semantic, run_id=run_id)
            policy_headings = semantic.get("policy_headings") if isinstance(semantic.get("policy_headings"), list) else []
            page_texts = {int(p.get("page_number") or 0): str(p.get("text") or "") for p in pages}
            link_proposals: dict[str, list[dict[str, Any]]] = {}
            if visual_rows:
                counts["visual_semantic_assets"] = counts.get("visual_semantic_assets", 0) + _extract_visual_asset_facts(
                    ingest_batch_id=ingest_batch_id,
                    run_id=run_id,
                    visual_assets=visual_rows,
                )
                step_counts["visual_semantics_asset"] = step_counts.get("visual_semantics_asset", 0) + 1

                mask_count, region_count = _segment_visual_assets(
                    ingest_batch_id=ingest_batch_id,
                    run_id=run_id,
                    authority_id=authority_id,
                    plan_cycle_id=plan_cycle_id,
                    document_id=document_id,
                    visual_assets=visual_rows,
                )
                counts["segmentation_masks"] += mask_count
                counts["visual_asset_regions"] += region_count
                step_counts["visual_segmentation"] = step_counts.get("visual_segmentation", 0) + 1

                vector_count = _vectorize_segmentation_masks(
                    ingest_batch_id=ingest_batch_id,
                    run_id=run_id,
                    document_id=document_id,
                    visual_assets=visual_rows,
                )
                counts["vector_paths"] += vector_count
                step_counts["visual_vectorization"] = step_counts.get("visual_vectorization", 0) + 1

                assertion_count = _extract_visual_region_assertions(
                    ingest_batch_id=ingest_batch_id,
                    run_id=run_id,
                    visual_assets=visual_rows,
                )
                counts["visual_semantic_assertions"] += assertion_count
                step_counts["visual_semantics_regions"] = step_counts.get("visual_semantics_regions", 0) + 1

                target_epsg = int(os.environ.get("TPA_GEOREF_TARGET_EPSG", "27700"))
                georef_attempts, georef_success, transform_count, projection_count = _auto_georef_visual_assets(
                    ingest_batch_id=ingest_batch_id,
                    run_id=run_id,
                    visual_assets=visual_rows,
                    target_epsg=target_epsg,
                )
                counts["georef_attempts"] += georef_attempts
                counts["georef_success"] += georef_success
                counts["transforms"] += transform_count
                counts["projection_artifacts"] += projection_count
                step_counts["visual_georef"] = step_counts.get("visual_georef", 0) + 1

                link_proposals, _ = _propose_visual_policy_links(
                    ingest_batch_id=ingest_batch_id,
                    run_id=run_id,
                    visual_assets=visual_rows,
                    policy_headings=policy_headings,
                    page_texts=page_texts,
                )

            step_counts["canonical_load"] = step_counts.get("canonical_load", 0) + 1

            identity_bundle, identity_tool_run_id, identity_errors = _extract_document_identity_status(
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                document_id=document_id,
                title=doc_metadata.get("title") or filename,
                filename=filename,
                content_type=content_type,
                block_rows=block_rows,
                evidence_ref_map=evidence_ref_map,
            )
            if identity_errors:
                errors.extend([f"document_identity:{err}" for err in identity_errors])
            if identity_bundle:
                counts["document_identity_status"] += 1
                step_counts["document_identity_status"] = step_counts.get("document_identity_status", 0) + 1
            sections, _, struct_errors = _llm_extract_policy_structure(
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                document_id=document_id,
                document_title=doc_metadata.get("title") or filename,
                blocks=block_rows,
                policy_headings=policy_headings,
            )
            if policy_headings and not sections:
                fallback_sections, _, fallback_errors = _llm_extract_policy_structure(
                    ingest_batch_id=ingest_batch_id,
                    run_id=run_id,
                    document_id=document_id,
                    document_title=doc_metadata.get("title") or filename,
                    blocks=block_rows,
                )
                sections = fallback_sections
                struct_errors.extend([f"policy_structure_fallback:{err}" for err in fallback_errors])
            if not policy_headings:
                sections = _merge_policy_headings(sections=sections, policy_headings=policy_headings, block_rows=block_rows)
            if struct_errors:
                errors.extend([f"policy_structure:{err}" for err in struct_errors])
            policy_sections, policy_clauses, definitions, targets, monitoring = _persist_policy_structure(
                document_id=document_id,
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                source_artifact_id=raw_artifact_id,
                sections=sections,
                block_rows=block_rows,
            )
            counts["policy_sections"] += len(policy_sections)
            counts["policy_clauses"] += len(policy_clauses)
            counts["definitions"] += len(definitions)
            counts["targets"] += len(targets)
            counts["monitoring"] += len(monitoring)
            step_counts["structural_llm"] = step_counts.get("structural_llm", 0) + 1

            matrix_count, scope_count = _persist_policy_logic_assets(
                document_id=document_id,
                run_id=run_id,
                sections=sections,
                policy_sections=policy_sections,
                standard_matrices=semantic.get("standard_matrices")
                if isinstance(semantic.get("standard_matrices"), list)
                else [],
                scope_candidates=semantic.get("scope_candidates")
                if isinstance(semantic.get("scope_candidates"), list)
                else [],
                evidence_ref_map=evidence_ref_map,
                block_rows=block_rows,
            )
            counts["policy_matrices"] = counts.get("policy_matrices", 0) + matrix_count
            counts["policy_scopes"] = counts.get("policy_scopes", 0) + scope_count
            if matrix_count or scope_count:
                step_counts["policy_logic_assets"] = step_counts.get("policy_logic_assets", 0) + 1

            policy_codes = [s.get("policy_code") for s in policy_sections if s.get("policy_code")]
            citations, mentions, conditions, edge_tool_run_ids, edge_errors = _llm_extract_edges(
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                policy_clauses=policy_clauses,
                policy_codes=policy_codes,
            )
            if edge_errors:
                errors.extend([f"policy_edges:{err}" for err in edge_errors])
            _persist_policy_edges(
                policy_sections=policy_sections,
                policy_clauses=policy_clauses,
                definitions=definitions,
                targets=targets,
                monitoring=monitoring,
                citations=citations,
                mentions=mentions,
                conditions=conditions,
                block_rows=block_rows,
                tool_run_ids=edge_tool_run_ids,
                run_id=run_id,
            )
            step_counts["edges_llm"] = step_counts.get("edges_llm", 0) + 1

            _persist_kg_nodes(
                document_id=document_id,
                chunks=chunk_rows,
                visual_assets=visual_rows,
                policy_sections=policy_sections,
                policy_clauses=policy_clauses,
                definitions=definitions,
                targets=targets,
                monitoring=monitoring,
            )

            if visual_rows:
                agent_count = _extract_visual_agent_findings(
                    ingest_batch_id=ingest_batch_id,
                    run_id=run_id,
                    visual_assets=visual_rows,
                )
                if agent_count:
                    counts["visual_semantic_agents"] = counts.get("visual_semantic_agents", 0) + agent_count

                links_by_asset, link_count = _persist_visual_policy_links_from_proposals(
                    run_id=run_id,
                    proposals_by_asset=link_proposals,
                    visual_assets=visual_rows,
                    policy_sections=policy_sections,
                )
                counts["visual_asset_links"] += link_count
                step_counts["visual_linking"] = step_counts.get("visual_linking", 0) + 1

                counts["unit_embeddings_visual"] += _embed_visual_assets(
                    ingest_batch_id=ingest_batch_id,
                    run_id=run_id,
                    visual_assets=visual_rows,
                    policy_sections=policy_sections,
                    links_by_asset=links_by_asset,
                )
                step_counts["visual_embeddings"] = step_counts.get("visual_embeddings", 0) + 1


            counts["unit_embeddings_chunk"] += _embed_units(
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                unit_type="chunk",
                rows=chunk_rows,
                text_key="text",
                id_key="chunk_id",
            )
            counts["unit_embeddings_policy_section"] += _embed_units(
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                unit_type="policy_section",
                rows=policy_sections,
                text_key="text",
                id_key="policy_section_id",
            )
            counts["unit_embeddings_policy_clause"] += _embed_units(
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                unit_type="policy_clause",
                rows=policy_clauses,
                text_key="text",
                id_key="policy_clause_id",
            )
            step_counts["embeddings"] = step_counts.get("embeddings", 0) + 1

        if counts.get("visual_semantic_assertions", 0) > 0:
            counts["unit_embeddings_visual_assertion"] += _embed_visual_assertions(
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
            )
            step_counts["visual_assertion_embeddings"] = step_counts.get("visual_assertion_embeddings", 0) + 1

        completed = _utc_now()
        if ingest_batch_id:
            visuals_present = counts.get("visual_assets", 0) > 0
            _finish_run_step(
                run_id=run_id,
                step_name="anchor_raw",
                status="success",
                outputs={"documents": step_counts.get("anchor_raw", 0)},
            )
            _finish_run_step(
                run_id=run_id,
                step_name="docling_parse",
                status="success" if step_counts.get("docling_parse", 0) > 0 else "partial",
                outputs={"documents": step_counts.get("docling_parse", 0)},
            )
            _finish_run_step(
                run_id=run_id,
                step_name="canonical_load",
                status="success" if step_counts.get("canonical_load", 0) > 0 else "partial",
                outputs={
                    "documents": step_counts.get("canonical_load", 0),
                    "pages": counts.get("pages", 0),
                    "layout_blocks": counts.get("layout_blocks", 0),
                    "tables": counts.get("tables", 0),
                    "vector_paths": counts.get("vector_paths", 0),
                    "chunks": counts.get("chunks", 0),
                    "visual_assets": counts.get("visual_assets", 0),
                },
            )
            _finish_run_step(
                run_id=run_id,
                step_name="document_identity_status",
                status="success" if step_counts.get("document_identity_status", 0) > 0 else "partial",
                outputs={
                    "documents": step_counts.get("document_identity_status", 0),
                },
            )
            _finish_run_step(
                run_id=run_id,
                step_name="visual_semantics_asset",
                status="success" if (not visuals_present or step_counts.get("visual_semantics_asset", 0) > 0) else "partial",
                outputs={
                    "visual_assets": counts.get("visual_assets", 0),
                    "visual_semantic_assets": counts.get("visual_semantic_assets", 0),
                },
            )
            _finish_run_step(
                run_id=run_id,
                step_name="visual_segmentation",
                status="success" if (not visuals_present or step_counts.get("visual_segmentation", 0) > 0) else "partial",
                outputs={
                    "visual_assets": counts.get("visual_assets", 0),
                    "segmentation_masks": counts.get("segmentation_masks", 0),
                    "visual_asset_regions": counts.get("visual_asset_regions", 0),
                },
            )
            _finish_run_step(
                run_id=run_id,
                step_name="visual_vectorization",
                status="success" if (not visuals_present or step_counts.get("visual_vectorization", 0) > 0) else "partial",
                outputs={
                    "vector_paths": counts.get("vector_paths", 0),
                },
            )
            _finish_run_step(
                run_id=run_id,
                step_name="visual_semantics_regions",
                status="success"
                if (not visuals_present or step_counts.get("visual_semantics_regions", 0) > 0)
                else "partial",
                outputs={
                    "visual_assets": counts.get("visual_assets", 0),
                    "visual_semantic_assertions": counts.get("visual_semantic_assertions", 0),
                },
            )
            _finish_run_step(
                run_id=run_id,
                step_name="visual_georef",
                status="success" if (not visuals_present or step_counts.get("visual_georef", 0) > 0) else "partial",
                outputs={
                    "georef_attempts": counts.get("georef_attempts", 0),
                    "georef_success": counts.get("georef_success", 0),
                    "transforms": counts.get("transforms", 0),
                    "projection_artifacts": counts.get("projection_artifacts", 0),
                },
            )
            _finish_run_step(
                run_id=run_id,
                step_name="visual_linking",
                status="success" if (not visuals_present or step_counts.get("visual_linking", 0) > 0) else "partial",
                outputs={
                    "visual_assets": counts.get("visual_assets", 0),
                    "visual_asset_links": counts.get("visual_asset_links", 0),
                },
            )
            _finish_run_step(
                run_id=run_id,
                step_name="visual_embeddings",
                status="success" if (not visuals_present or step_counts.get("visual_embeddings", 0) > 0) else "partial",
                outputs={
                    "visual_assets": counts.get("visual_assets", 0),
                    "unit_embeddings_visual": counts.get("unit_embeddings_visual", 0),
                },
            )
            _finish_run_step(
                run_id=run_id,
                step_name="visual_assertion_embeddings",
                status="success"
                if (not visuals_present or step_counts.get("visual_assertion_embeddings", 0) > 0)
                else "partial",
                outputs={
                    "unit_embeddings_visual_assertion": counts.get("unit_embeddings_visual_assertion", 0),
                },
            )
            _finish_run_step(
                run_id=run_id,
                step_name="structural_llm",
                status="success" if step_counts.get("structural_llm", 0) > 0 else "partial",
                outputs={
                    "policy_sections": counts.get("policy_sections", 0),
                    "policy_clauses": counts.get("policy_clauses", 0),
                    "definitions": counts.get("definitions", 0),
                    "targets": counts.get("targets", 0),
                    "monitoring": counts.get("monitoring", 0),
                },
            )
            _finish_run_step(
                run_id=run_id,
                step_name="edges_llm",
                status="success" if step_counts.get("edges_llm", 0) > 0 else "partial",
                outputs={"documents": step_counts.get("edges_llm", 0)},
            )
            _finish_run_step(
                run_id=run_id,
                step_name="embeddings",
                status="success" if step_counts.get("embeddings", 0) > 0 else "partial",
                outputs={
                    "unit_embeddings_chunk": counts.get("unit_embeddings_chunk", 0),
                    "unit_embeddings_policy_section": counts.get("unit_embeddings_policy_section", 0),
                    "unit_embeddings_policy_clause": counts.get("unit_embeddings_policy_clause", 0),
                },
            )
        outputs = {"counts": counts, "errors": errors[:20]}
        run_status = "success" if not errors else "partial"
        if run_id:
            _finish_ingest_run(
                run_id=run_id,
                status=run_status,
                outputs=outputs,
            )
            scope_key = plan_cycle_id or authority_id
            if scope_key and run_status == "success":
                scope_type = "plan_cycle" if plan_cycle_id else "authority"
                _set_ingest_run_alias(
                    scope_type=scope_type,
                    scope_key=str(scope_key),
                    alias="latest_good",
                    run_id=run_id,
                    notes="Auto-set on successful ingest run.",
                )
        _update_job_status(ingest_job_id=ingest_job_id, status="success" if not errors else "partial", outputs=outputs, completed_at=completed)
        if ingest_batch_id:
            _update_ingest_batch_progress(
                ingest_batch_id=ingest_batch_id,
                status="success" if not errors else "partial",
                counts=counts,
                errors=errors,
                document_ids=[],
                plan_cycle_id=plan_cycle_id,
                progress={"phase": "complete"},
            )
        return {"status": "complete", "counts": counts, "errors": errors}
    except Exception as exc:  # noqa: BLE001
        if "run_id" in locals() and run_id:
            _finish_ingest_run(run_id=run_id, status="error", outputs={}, error_text=str(exc))
        _update_job_status(ingest_job_id=ingest_job_id, status="error", error_text=str(exc), completed_at=_utc_now())
        return {"status": "error", "error": str(exc)}
    finally:
        shutdown_db_pool()
