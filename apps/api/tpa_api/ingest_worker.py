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
from uuid import uuid4

import httpx
from celery import Celery

from PIL import Image

from .blob_store import minio_client_or_none, read_blob_bytes, write_blob_bytes
from .db import _db_execute, _db_execute_returning, _db_fetch_all, _db_fetch_one, init_db_pool, shutdown_db_pool
from .model_clients import _embed_multimodal_sync, _embed_texts_sync
from .prompting import _llm_structured_sync
from .policy_utils import _normalize_policy_speech_act
from .time_utils import _utc_now
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
    timeout = float(os.environ.get("TPA_DOCPARSE_TIMEOUT_SECONDS", "300"))
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
        for key in ("width", "height"):
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


def _persist_layout_blocks(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    pages: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    page_texts = {int(p.get("page_number") or 0): str(p.get("text") or "") for p in pages}
    rows: list[dict[str, Any]] = []
    for block in blocks:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        page_number = int(block.get("page_number") or 0)
        layout_block_id = str(uuid4())
        block_id = str(block.get("block_id") or layout_block_id)
        span_start, span_end, span_quality = _find_span(page_texts.get(page_number, ""), text)
        evidence_ref_id = str(uuid4())
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
                json.dumps({}, ensure_ascii=False),
            ),
        )
        _db_execute(
            "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
            (evidence_ref_id, "layout_block", layout_block_id, block_id, run_id),
        )
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
                "evidence_ref": f"chunk::{chunk_id}::{fragment}",
                "type": block.get("type"),
                "section_path": block.get("section_path"),
                "span_start": block.get("span_start"),
                "span_end": block.get("span_end"),
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
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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
        }
        now = _utc_now()
        _db_execute(
            """
            INSERT INTO visual_assets (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              asset_type, blob_path, metadata, created_at, updated_at
            )
            VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s, %s)
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
                json.dumps(metadata, ensure_ascii=False),
                now,
                now,
            ),
        )
        evidence_ref_id = str(uuid4())
        _db_execute(
            """
            INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id)
            VALUES (%s, %s, %s, %s, %s::uuid)
            """,
            (evidence_ref_id, "visual_asset", asset_id, "image", run_id),
        )
        rows.append(
            {
                "visual_asset_id": asset_id,
                "page_number": asset.get("page_number"),
                "metadata": metadata,
                "blob_path": blob_path,
                "evidence_ref_id": evidence_ref_id,
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

    exemplars = semantic.get("design_exemplars") if isinstance(semantic.get("design_exemplars"), list) else []
    for ex in exemplars:
        if not isinstance(ex, dict):
            continue
        image_ref = ex.get("image_ref")
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
                "design_exemplar",
                None,
                None,
                row.get("evidence_ref_id"),
                json.dumps(ex, ensure_ascii=False),
            ),
        )

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
    timeout = float(os.environ.get("TPA_SEGMENTATION_TIMEOUT_SECONDS", "180"))
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

            region_meta = {
                "region_blob_path": region_blob_path,
                "polygon": mask.get("polygon"),
                "confidence": mask.get("confidence"),
            }
            _db_execute(
                """
                INSERT INTO visual_asset_regions (
                  id, visual_asset_id, run_id, region_type, bbox, bbox_quality,
                  mask_id, caption_text, metadata_jsonb, created_at
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s::uuid, %s, %s::jsonb, %s)
                """,
                (
                    str(uuid4()),
                    visual_asset_id,
                    run_id,
                    "mask_crop",
                    json.dumps(bbox, ensure_ascii=False) if bbox else None,
                    bbox_quality,
                    mask_id,
                    caption,
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


def _link_visual_assets_to_policies(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
    policy_sections: list[dict[str, Any]],
    page_texts: dict[int, str],
) -> tuple[dict[str, list[str]], int]:
    if not visual_assets:
        return {}, 0
    candidates = [
        {
            "policy_code": s.get("policy_code"),
            "title": s.get("title"),
            "snippet": _truncate_text(s.get("text"), 240),
        }
        for s in policy_sections
        if s.get("policy_code")
    ]
    if not candidates:
        return {}, 0

    section_by_code = {s.get("policy_code"): s for s in policy_sections if s.get("policy_code")}
    links_by_asset: dict[str, list[str]] = {}
    link_count = 0

    prompt_id = "visual_asset_link_v1"
    system_template = (
        "You are linking visual assets to planning policies. "
        "Return ONLY JSON with shape: "
        '{ "links": [ { "policy_code": "string", "confidence": "low|medium|high", "rationale": "string" } ] }. '
        "Only include codes that are explicitly referenced or clearly relevant."
    )

    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        if not visual_asset_id:
            continue
        metadata = asset.get("metadata") or {}
        page_number = int(asset.get("page_number") or 0)
        caption = metadata.get("caption") or (metadata.get("classification") or {}).get("caption_hint")
        page_text = _truncate_text(page_texts.get(page_number), 1200)

        payload = {
            "asset_id": visual_asset_id,
            "asset_type": metadata.get("asset_type"),
            "caption": caption,
            "page_text": page_text,
            "policy_candidates": candidates,
        }
        obj, tool_run_id, errs = _llm_structured_sync(
            prompt_id=prompt_id,
            prompt_version=1,
            prompt_name="Visual policy linker",
            purpose="Link visual assets to relevant policy sections.",
            system_template=system_template,
            user_payload=payload,
            time_budget_seconds=60.0,
            temperature=0.2,
            max_tokens=600,
            output_schema_ref="schemas/VisualAssetLinkParseResult.schema.json",
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
            if not policy_code or policy_code not in section_by_code:
                continue
            section_id = section_by_code[policy_code].get("policy_section_id")
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
                    visual_asset_id,
                    run_id,
                    "policy_section",
                    str(section_id),
                    "policy_reference",
                    asset.get("evidence_ref_id"),
                    tool_run_id,
                    json.dumps(
                        {
                            "policy_code": policy_code,
                            "confidence": link.get("confidence"),
                            "rationale": link.get("rationale"),
                        },
                        ensure_ascii=False,
                    ),
                    _utc_now(),
                ),
            )
            links_by_asset.setdefault(visual_asset_id, []).append(str(section_id))
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
    slices: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for block in blocks:
        text = str(block.get("text") or "")
        block_len = len(text)
        if current and (current_chars + block_len > max_chars or len(current) >= max_blocks):
            slices.append(current)
            current = []
            current_chars = 0
        current.append(block)
        current_chars += block_len
    if current:
        slices.append(current)
    return slices


def _llm_extract_policy_structure(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    document_id: str,
    document_title: str,
    blocks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    if not blocks:
        return [], [], ["no_blocks"]
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
            temperature=0.3,
            max_tokens=1600,
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
    props: dict[str, Any] | None = None,
    evidence_ref_id: str | None = None,
    tool_run_id: str | None = None,
) -> None:
    _db_execute(
        """
        INSERT INTO kg_edge (
          edge_id, src_id, dst_id, edge_type, props_jsonb,
          evidence_ref_id, tool_run_id, run_id
        )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::uuid, %s::uuid, %s::uuid)
        """,
        (
            str(uuid4()),
            src_id,
            dst_id,
            edge_type,
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
                json.dumps({}, ensure_ascii=False),
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
                "policy_code": section.get("policy_code"),
                "title": section.get("title"),
                "text": section_text,
                "evidence_ref_id": evidence_ref_id,
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
                  span_start, span_end, span_quality, speech_act_jsonb,
                  subject, object, evidence_ref_id, source_artifact_id, metadata_jsonb
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::uuid, %s::uuid, %s::jsonb)
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
                    clause.get("subject"),
                    clause.get("object"),
                    clause_evidence_ref_id,
                    source_artifact_id,
                    json.dumps({}, ensure_ascii=False),
                ),
            )
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (clause_evidence_ref_id, "policy_clause", clause_id, clause.get("clause_ref") or clause_id, run_id),
            )
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    if not policy_clauses:
        return [], [], [], ["no_clauses"]
    prompt_id = "policy_edge_parse_v1"
    system_template = (
        "You are extracting citations and mentions from planning policy clauses.\n"
        "Return ONLY JSON with shape:\n"
        "{\n"
        '  "citations": [\n'
        '    {"source_clause_id": "uuid", "target_policy_code": "string", "confidence": "low|medium|high"}\n'
        "  ],\n"
        '  "mentions": [\n'
        '    {"source_clause_id": "uuid", "mention_text": "string", "mention_type": "place|designation|constraint|other", "confidence": "low|medium|high"}\n'
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Only cite policy codes that appear in the provided policy_codes list.\n"
        "- Use mention_type based on context; do not invent entities.\n"
    )

    tool_run_ids: list[str] = []
    errors: list[str] = []
    citations: list[dict[str, Any]] = []
    mentions: list[dict[str, Any]] = []

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
            purpose="Extract policy citations and place/constraint mentions from clauses.",
            system_template=system_template,
            user_payload=payload,
            time_budget_seconds=90.0,
            temperature=0.2,
            max_tokens=1200,
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

    return citations, mentions, tool_run_ids, errors


def _persist_policy_edges(
    *,
    policy_sections: list[dict[str, Any]],
    policy_clauses: list[dict[str, Any]],
    definitions: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    monitoring: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    mentions: list[dict[str, Any]],
    tool_run_ids: list[str],
    run_id: str | None,
) -> None:
    section_by_code = {
        s.get("policy_code"): s.get("policy_section_id")
        for s in policy_sections
        if s.get("policy_code") and s.get("policy_section_id")
    }
    clause_ref_map = {c.get("policy_clause_id"): c for c in policy_clauses if c.get("policy_clause_id")}
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
            props={"confidence": cite.get("confidence")},
            evidence_ref_id=src.get("evidence_ref_id") if src else None,
            tool_run_id=tool_run_id,
        )

    for mention in mentions:
        source_clause_id = mention.get("source_clause_id")
        mention_text = mention.get("mention_text")
        if not source_clause_id or not mention_text:
            continue
        slug = _slugify(str(mention_text))
        node_id = f"mention::{slug}"
        _ensure_kg_node(
            node_id=node_id,
            node_type="Mention",
            canonical_fk=None,
            props={"mention_text": mention_text, "mention_type": mention.get("mention_type")},
        )
        src = clause_ref_map.get(source_clause_id)
        _insert_kg_edge(
            src_id=f"policy_clause::{source_clause_id}",
            dst_id=node_id,
            edge_type="MENTIONS",
            run_id=run_id,
            props={"confidence": mention.get("confidence")},
            evidence_ref_id=src.get("evidence_ref_id") if src else None,
            tool_run_id=tool_run_id,
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
            "pages": 0,
            "layout_blocks": 0,
            "tables": 0,
            "vector_paths": 0,
            "chunks": 0,
            "visual_assets": 0,
            "segmentation_masks": 0,
            "visual_asset_regions": 0,
            "visual_asset_links": 0,
            "policy_sections": 0,
            "policy_clauses": 0,
            "definitions": 0,
            "targets": 0,
            "monitoring": 0,
            "unit_embeddings_chunk": 0,
            "unit_embeddings_policy_section": 0,
            "unit_embeddings_policy_clause": 0,
            "unit_embeddings_visual": 0,
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
                step_name="visual_segmentation",
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

            blocks = bundle.get("layout_blocks") if isinstance(bundle.get("layout_blocks"), list) else []
            block_rows = _persist_layout_blocks(
                document_id=document_id,
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                source_artifact_id=raw_artifact_id,
                pages=pages,
                blocks=blocks,
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
            )
            counts["visual_assets"] += len(visual_rows)
            _persist_visual_features(visual_assets=visual_rows, run_id=run_id)

            semantic = bundle.get("semantic") if isinstance(bundle.get("semantic"), dict) else {}
            _persist_visual_semantic_features(visual_assets=visual_rows, semantic=semantic, run_id=run_id)

            step_counts["canonical_load"] = step_counts.get("canonical_load", 0) + 1

            sections, _, struct_errors = _llm_extract_policy_structure(
                ingest_batch_id=ingest_batch_id,
                run_id=run_id,
                document_id=document_id,
                document_title=doc_metadata.get("title") or filename,
                blocks=block_rows,
            )
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

            policy_codes = [s.get("policy_code") for s in policy_sections if s.get("policy_code")]
            citations, mentions, edge_tool_run_ids, edge_errors = _llm_extract_edges(
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

            page_texts = {int(p.get("page_number") or 0): str(p.get("text") or "") for p in pages}
            if visual_rows:
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

                links_by_asset, link_count = _link_visual_assets_to_policies(
                    ingest_batch_id=ingest_batch_id,
                    run_id=run_id,
                    visual_assets=visual_rows,
                    policy_sections=policy_sections,
                    page_texts=page_texts,
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
        if run_id:
            _finish_ingest_run(
                run_id=run_id,
                status="success" if not errors else "partial",
                outputs=outputs,
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
