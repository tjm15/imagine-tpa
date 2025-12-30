from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

from langgraph.checkpoint.memory import MemorySaver

from tpa_api.db import init_db_pool, _db_fetch_all, _db_fetch_one
from tpa_api.ingestion.ingestion_graph import build_stage_graph
from tpa_api.ingestion.run_state import load_ingest_run_context


def _clean_db_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, UUID):
                item[key] = str(value)
            else:
                item[key] = value
        cleaned.append(item)
    return cleaned


async def run_stage_for_run(run_id: str, stage: str) -> dict[str, Any]:
    init_db_pool()
    run_ctx = load_ingest_run_context(run_id)
    ingest_batch_id = run_ctx.get("ingest_batch_id")
    if not ingest_batch_id:
        return {"status": "error", "error": "missing_ingest_batch_id"}

    docs = _clean_db_rows(
        _db_fetch_all(
            """
            SELECT id, authority_id, plan_cycle_id, metadata, raw_source_uri, raw_content_type, raw_artifact_id, blob_path
            FROM documents
            WHERE ingest_batch_id = %s::uuid
            ORDER BY created_at ASC
            """,
            (str(ingest_batch_id),),
        )
    )
    if not docs:
        return {"status": "error", "error": "no_documents_for_run"}

    missing_bundles: list[str] = []
    for doc in docs:
        doc_id = doc.get("id")
        if not doc_id:
            continue
        bundle = _db_fetch_one(
            """
            SELECT id
            FROM parse_bundles
            WHERE document_id = %s::uuid
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (str(doc_id),),
        )
        if not bundle:
            missing_bundles.append(str(doc_id))
    if missing_bundles:
        return {
            "status": "error",
            "error": "missing_parse_bundle",
            "missing_documents": missing_bundles,
        }

    graph = build_stage_graph(checkpointer=MemorySaver(), stage=stage)
    processed = 0
    failures: list[str] = []

    for doc in docs:
        doc_id = doc.get("id")
        if not doc_id:
            continue
        filename = Path(doc.get("raw_source_uri") or doc.get("blob_path") or f"{doc_id}.pdf").name
        initial_state = {
            "run_id": run_id,
            "ingest_batch_id": str(ingest_batch_id),
            "authority_id": str(doc.get("authority_id") or run_ctx.get("authority_id")),
            "plan_cycle_id": doc.get("plan_cycle_id") or run_ctx.get("plan_cycle_id"),
            "document_id": str(doc_id),
            "doc_metadata": doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {},
            "filename": filename,
            "content_type": doc.get("raw_content_type"),
            "raw_artifact_id": doc.get("raw_artifact_id"),
            "counts": {},
            "steps_completed": [],
            "errors": [],
        }
        try:
            config = {"configurable": {"thread_id": str(doc_id)}}
            final_state = await graph.ainvoke(initial_state, config)
            if isinstance(final_state, dict) and final_state.get("error"):
                raise RuntimeError(str(final_state.get("error")))
            processed += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{doc_id}: {exc}")

    return {
        "status": "ok",
        "run_id": run_id,
        "stage": stage,
        "documents_processed": processed,
        "failures": failures,
    }


def run_stage_for_run_sync(run_id: str, stage: str) -> dict[str, Any]:
    return asyncio.run(run_stage_for_run(run_id, stage))
