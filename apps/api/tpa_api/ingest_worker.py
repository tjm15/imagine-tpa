from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from celery import Celery

from .blob_store import minio_client_or_none
from .db import _db_execute, _db_execute_returning, _db_fetch_all, _db_fetch_one, init_db_pool, shutdown_db_pool
from .model_clients import _embed_texts_sync
from .time_utils import _utc_now
from .vector_utils import _vector_literal
from .services.ingest import (
    _authority_packs_root,
    _derive_filename_for_url,
    _is_http_url,
    _llm_parse_policy_clauses_for_section_sync,
    _load_authority_pack_manifest,
    _normalize_authority_pack_documents,
    _update_ingest_batch_progress,
    _web_automation_ingest_url,
)


BROKER_URL = os.environ.get("TPA_REDIS_URL") or "redis://localhost:6379/0"
celery_app = Celery("tpa_ingest", broker=BROKER_URL, backend=BROKER_URL)


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
    blob_path: str,
    metadata: dict[str, Any],
) -> str:
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
        return str(existing["id"])
    doc_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO documents (
          id, authority_id, ingest_batch_id, plan_cycle_id,
          document_status, weight_hint, effective_from, effective_to,
          metadata, blob_path
        )
        VALUES (%s, %s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s)
        """,
        (
            doc_id,
            authority_id,
            ingest_batch_id,
            plan_cycle_id,
            metadata.get("status"),
            metadata.get("weight_hint"),
            metadata.get("effective_from"),
            metadata.get("effective_to"),
            json.dumps(metadata, ensure_ascii=False),
            blob_path,
        ),
    )
    return doc_id


def _persist_tool_runs(*, ingest_batch_id: str, tool_runs: list[dict[str, Any]]) -> list[str]:
    tool_run_ids: list[str] = []
    for tr in tool_runs:
        tool_run_id = str(uuid4())
        tool_run_ids.append(tool_run_id)
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
              started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                tool_run_id,
                ingest_batch_id,
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
    document_id: str,
    schema_version: str,
    blob_path: str,
) -> str:
    bundle_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO parse_bundles (
          id, ingest_job_id, ingest_batch_id, document_id,
          schema_version, blob_path, status, metadata_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s::jsonb, %s)
        """,
        (
            bundle_id,
            ingest_job_id,
            ingest_batch_id,
            document_id,
            schema_version,
            blob_path,
            "stored",
            json.dumps({}, ensure_ascii=False),
            _utc_now(),
        ),
    )
    return bundle_id


def _persist_pages(*, document_id: str, pages: list[dict[str, Any]]) -> None:
    for page in pages:
        page_number = int(page.get("page_number") or 0)
        if page_number <= 0:
            continue
        _db_execute(
            """
            INSERT INTO pages (id, document_id, page_number, metadata)
            VALUES (%s, %s::uuid, %s, %s::jsonb)
            ON CONFLICT (document_id, page_number) DO NOTHING
            """,
            (str(uuid4()), document_id, page_number, json.dumps({}, ensure_ascii=False)),
        )


def _persist_chunks(*, document_id: str, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunk_rows: list[dict[str, Any]] = []
    for block in blocks:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        chunk_id = str(uuid4())
        page_number = block.get("page_number")
        fragment = str(block.get("block_id") or "block")
        _db_execute(
            """
            INSERT INTO chunks (id, document_id, page_number, text, bbox, type, section_path, metadata)
            VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
            """,
            (
                chunk_id,
                document_id,
                page_number,
                text,
                json.dumps(block.get("bbox"), ensure_ascii=False) if block.get("bbox") is not None else None,
                block.get("type"),
                block.get("section_path"),
                json.dumps({"evidence_ref_fragment": fragment}, ensure_ascii=False),
            ),
        )
        evidence_ref_id = str(uuid4())
        _db_execute(
            "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id) VALUES (%s, %s, %s, %s)",
            (evidence_ref_id, "chunk", chunk_id, fragment),
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
            }
        )
    return chunk_rows


def _persist_visual_assets(
    *,
    document_id: str,
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
            "width": asset.get("width"),
            "height": asset.get("height"),
        }
        _db_execute(
            """
            INSERT INTO visual_assets (id, document_id, page_number, asset_type, blob_path, metadata)
            VALUES (%s, %s::uuid, %s, %s, %s, %s::jsonb)
            """,
            (
                asset_id,
                document_id,
                asset.get("page_number"),
                asset.get("asset_type") or "unknown",
                blob_path,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        evidence_ref_id = str(uuid4())
        _db_execute(
            """
            INSERT INTO evidence_refs (id, source_type, source_id, fragment_id)
            VALUES (%s, %s, %s, %s)
            """,
            (evidence_ref_id, "visual_asset", asset_id, "image"),
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


def _persist_visual_features(*, visual_assets: list[dict[str, Any]]) -> None:
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        if not visual_asset_id:
            continue
        metadata = asset.get("metadata") or {}
        classification = metadata.get("classification") or {}
        feature_type = classification.get("asset_type") or "visual_classification"
        _db_execute(
            """
            INSERT INTO visual_features (id, visual_asset_id, feature_type, geometry_jsonb, confidence, evidence_ref_id, metadata_jsonb)
            VALUES (%s, %s::uuid, %s, %s::jsonb, %s, %s::uuid, %s::jsonb)
            """,
            (
                str(uuid4()),
                visual_asset_id,
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
            INSERT INTO visual_features (id, visual_asset_id, feature_type, geometry_jsonb, confidence, evidence_ref_id, metadata_jsonb)
            VALUES (%s, %s::uuid, %s, %s::jsonb, %s, %s::uuid, %s::jsonb)
            """,
            (
                str(uuid4()),
                row.get("visual_asset_id"),
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
            INSERT INTO visual_features (id, visual_asset_id, feature_type, geometry_jsonb, confidence, evidence_ref_id, metadata_jsonb)
            VALUES (%s, %s::uuid, %s, %s::jsonb, %s, %s::uuid, %s::jsonb)
            """,
            (
                str(uuid4()),
                row.get("visual_asset_id"),
                "visual_constraint",
                None,
                None,
                row.get("evidence_ref_id"),
                json.dumps(vc, ensure_ascii=False),
            ),
        )


def _embed_chunks(*, ingest_batch_id: str, chunks: list[dict[str, Any]]) -> int:
    candidates = [
        (c.get("chunk_id"), c.get("text"))
        for c in chunks
        if isinstance(c.get("text"), str) and c.get("text").strip() and c.get("chunk_id")
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
          id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
          started_at, ended_at, confidence_hint, uncertainty_note
        )
        VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
        """,
        (
            tool_run_id,
            ingest_batch_id,
            "embed_chunks",
            json.dumps({"chunk_count": len(embeddings)}, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
            "running",
            _utc_now(),
            None,
            "medium",
            "Embedding chunks for retrieval.",
        ),
    )
    inserted = 0
    for (chunk_id, _), vec in zip(candidates, embeddings, strict=True):
        _db_execute(
            """
            INSERT INTO chunk_embeddings (id, chunk_id, embedding, embedding_model_id, created_at, tool_run_id)
            VALUES (%s, %s::uuid, %s::vector, %s, %s, %s::uuid)
            ON CONFLICT (chunk_id, embedding_model_id) DO NOTHING
            """,
            (
                str(uuid4()),
                chunk_id,
                _vector_literal(vec),
                os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B"),
                _utc_now(),
                tool_run_id,
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


def _persist_policies(
    *,
    authority_id: str,
    plan_cycle_id: str,
    ingest_batch_id: str,
    document_id: str,
    policy_headings: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> tuple[int, int]:
    if not policy_headings:
        return 0, 0
    block_index_map = {c.get("fragment"): idx for idx, c in enumerate(chunks)}
    ordered_blocks = sorted([c for c in chunks if c.get("fragment")], key=lambda c: block_index_map.get(c.get("fragment"), 10**9))
    policy_created = 0
    clause_created = 0
    for heading in policy_headings:
        block_id = heading.get("block_id")
        if not isinstance(block_id, str):
            continue
        start_idx = block_index_map.get(block_id)
        if start_idx is None:
            continue
        end_idx = len(ordered_blocks)
        for other in policy_headings:
            other_id = other.get("block_id")
            if not isinstance(other_id, str):
                continue
            other_idx = block_index_map.get(other_id)
            if other_idx is None:
                continue
            if other_idx > start_idx and other_idx < end_idx:
                end_idx = other_idx
        block_slice = ordered_blocks[start_idx:end_idx]
        policy_text = "\n\n".join([b.get("text") or "" for b in block_slice]).strip()
        if not policy_text:
            continue
        policy_id = str(uuid4())
        policy_ref = heading.get("policy_code") if isinstance(heading.get("policy_code"), str) else None
        policy_title = heading.get("policy_title") if isinstance(heading.get("policy_title"), str) else None
        _db_execute(
            """
            INSERT INTO policies (
              id, authority_id, ingest_batch_id, plan_cycle_id, policy_status, policy_weight_hint,
              effective_from, effective_to, applicability_jsonb, is_active, text, metadata
            )
            VALUES (%s, %s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb, true, %s, %s::jsonb)
            """,
            (
                policy_id,
                authority_id,
                ingest_batch_id,
                plan_cycle_id,
                None,
                None,
                None,
                None,
                json.dumps({}, ensure_ascii=False),
                policy_text,
                json.dumps({"policy_ref": policy_ref, "policy_title": policy_title, "document_id": document_id}, ensure_ascii=False),
            ),
        )
        policy_created += 1
        source_chunks = []
        for b in block_slice:
            source_chunks.append(
                {
                    "evidence_ref": b.get("evidence_ref"),
                    "type": b.get("type"),
                    "section_path": b.get("section_path"),
                    "text": b.get("text"),
                }
            )
        clauses, _, _, _ = _llm_parse_policy_clauses_for_section_sync(
            ingest_batch_id=ingest_batch_id,
            authority_id=authority_id,
            plan_cycle_id=plan_cycle_id,
            policy_ref=str(policy_ref or ""),
            policy_title=policy_title,
            source_chunks=source_chunks,
        )
        for clause in clauses:
            clause_id = str(uuid4())
            _db_execute(
                """
                INSERT INTO policy_clauses (id, policy_id, clause_ref, text, metadata)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb)
                """,
                (
                    clause_id,
                    policy_id,
                    clause.get("clause_ref"),
                    clause.get("text") or "",
                    json.dumps({"speech_act": clause.get("speech_act")}, ensure_ascii=False),
                ),
            )
            clause_created += 1
    return policy_created, clause_created


def _persist_kg_nodes(*, document_id: str, chunks: list[dict[str, Any]], visual_assets: list[dict[str, Any]]) -> None:
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

        counts = {"documents_seen": 0, "chunks": 0, "visual_assets": 0, "policies": 0, "policy_clauses": 0}
        errors: list[str] = []

        for doc in documents:
            counts["documents_seen"] += 1
            rel_path = doc.get("file_path")
            source_url = doc.get("source_url") or doc.get("url")
            if not source_url and _is_http_url(rel_path):
                source_url = str(rel_path)
                rel_path = None

            data_bytes: bytes | None = None
            filename = None
            if source_url:
                result = _web_automation_ingest_url(url=source_url, ingest_batch_id=ingest_batch_id or str(uuid4()))
                if not result.get("ok"):
                    errors.append(f"web_ingest_failed:{source_url}")
                    continue
                data_bytes = result.get("bytes")
                filename = result.get("filename") or _derive_filename_for_url(source_url, content_type=result.get("content_type"))
            if data_bytes is None and rel_path:
                pack_path = Path(pack_dir or "") / str(rel_path)
                if not pack_path.exists():
                    errors.append(f"missing_file:{pack_path}")
                    continue
                data_bytes = pack_path.read_bytes()
                filename = pack_path.name

            if data_bytes is None:
                errors.append("missing_document_bytes")
                continue

            blob_path = source_url or str(rel_path or filename or "document.pdf")
            doc_metadata = {
                "title": doc.get("title") or (filename or "Document"),
                "source_url": source_url,
                "document_type": doc.get("document_type"),
            }

            document_id = _ensure_document_row(
                authority_id=authority_id,
                plan_cycle_id=plan_cycle_id,
                ingest_batch_id=ingest_batch_id,
                blob_path=blob_path,
                metadata=doc_metadata,
            )

            parse_result = _call_docparse_bundle(
                file_bytes=data_bytes,
                filename=filename or "document.pdf",
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

            bundle = _load_parse_bundle(bundle_path)
            _insert_parse_bundle_record(
                ingest_job_id=ingest_job_id,
                ingest_batch_id=ingest_batch_id,
                document_id=document_id,
                schema_version=bundle.get("schema_version") or "2.0",
                blob_path=bundle_path,
            )

            tool_runs = bundle.get("tool_runs") if isinstance(bundle.get("tool_runs"), list) else []
            _persist_tool_runs(ingest_batch_id=ingest_batch_id, tool_runs=tool_runs)

            pages = bundle.get("pages") if isinstance(bundle.get("pages"), list) else []
            _persist_pages(document_id=document_id, pages=pages)

            blocks = bundle.get("layout_blocks") if isinstance(bundle.get("layout_blocks"), list) else []
            chunk_rows = _persist_chunks(document_id=document_id, blocks=blocks)
            counts["chunks"] += len(chunk_rows)

            visual_assets = bundle.get("visual_assets") if isinstance(bundle.get("visual_assets"), list) else []
            visual_rows = _persist_visual_assets(document_id=document_id, visual_assets=visual_assets)
            counts["visual_assets"] += len(visual_rows)
            _persist_visual_features(visual_assets=visual_rows)

            _embed_chunks(ingest_batch_id=ingest_batch_id, chunks=chunk_rows)

            semantic = bundle.get("semantic") if isinstance(bundle.get("semantic"), dict) else {}
            _persist_visual_semantic_features(visual_assets=visual_rows, semantic=semantic)
            _update_document_semantic_metadata(document_id=document_id, semantic=semantic)
            policy_headings = semantic.get("policy_headings") if isinstance(semantic.get("policy_headings"), list) else []
            policies_created, clauses_created = _persist_policies(
                authority_id=authority_id,
                plan_cycle_id=plan_cycle_id,
                ingest_batch_id=ingest_batch_id,
                document_id=document_id,
                policy_headings=policy_headings,
                chunks=chunk_rows,
            )
            counts["policies"] += policies_created
            counts["policy_clauses"] += clauses_created

            _persist_kg_nodes(document_id=document_id, chunks=chunk_rows, visual_assets=visual_rows)

        completed = _utc_now()
        outputs = {"counts": counts, "errors": errors[:20]}
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
        _update_job_status(ingest_job_id=ingest_job_id, status="error", error_text=str(exc), completed_at=_utc_now())
        return {"status": "error", "error": str(exc)}
    finally:
        shutdown_db_pool()
