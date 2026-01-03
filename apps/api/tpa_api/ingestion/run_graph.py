import os
import sys
import asyncio
import json
import mimetypes
from pathlib import Path
from typing import Any
from langgraph.checkpoint.memory import MemorySaver
from tpa_api.ingestion.ingestion_graph import build_ingestion_graph
from tpa_api.ingestion.run_state import create_ingest_run
from tpa_api.db import init_db_pool, _db_fetch_one, _db_fetch_all
from tpa_api.blob_store import read_blob_bytes


def _coerce_inputs(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:  # noqa: BLE001
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _coerce_doc_entry(raw: object) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return {"file_path": raw, "title": Path(raw).stem, "source": "authority_pack"}
    return None


def _ensure_filename(name: str | None) -> str:
    if not name:
        return "document.pdf"
    suffix = Path(name).suffix
    return name if suffix else f"{name}.pdf"


def _guess_content_type(path: Path, override: str | None = None) -> str:
    if override:
        return override
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


async def run_graph_for_job(job_id: str) -> dict[str, object]:
    init_db_pool()

    job = _db_fetch_one("SELECT * FROM ingest_jobs WHERE id = %s::uuid", (job_id,))
    if not job:
        return {"status": "error", "error": f"Job {job_id} not found."}

    docs = _db_fetch_all(
        """
        SELECT id, authority_id, plan_cycle_id, raw_blob_path, raw_source_uri, raw_content_type, metadata
        FROM documents
        WHERE ingest_batch_id = %s::uuid
        ORDER BY created_at ASC
        """,
        (str(job["ingest_batch_id"]),),
    )

    input_docs: list[dict[str, Any]] = []
    failures: list[str] = []
    if not docs:
        inputs = _coerce_inputs(job.get("inputs_jsonb") or job.get("inputs") or {})
        raw_docs = inputs.get("documents")
        pack_dir = inputs.get("pack_dir")
        pack_root = Path(pack_dir) if isinstance(pack_dir, str) else None
        if isinstance(raw_docs, list):
            for raw_doc in raw_docs:
                entry = _coerce_doc_entry(raw_doc)
                if not entry:
                    continue
                file_path = entry.get("file_path")
                source_url = entry.get("source_url")
                metadata = dict(entry)
                metadata.pop("file_path", None)
                metadata.pop("source_url", None)
                if file_path:
                    path = Path(str(file_path))
                    if pack_root and not path.is_absolute():
                        path = pack_root / path
                    if not path.exists():
                        failures.append(f"missing_file:{file_path}")
                        continue
                    try:
                        file_bytes = path.read_bytes()
                    except Exception as exc:  # noqa: BLE001
                        failures.append(f"read_failed:{file_path}:{exc}")
                        continue
                    input_docs.append(
                        {
                            "file_bytes": file_bytes,
                            "filename": path.name,
                            "metadata": metadata,
                            "raw_source_uri": source_url or str(file_path),
                            "raw_content_type": _guess_content_type(path, entry.get("content_type")),
                            "source_url": source_url,
                        }
                    )
                    continue
                if source_url:
                    try:
                        from tpa_api.services.ingest import _web_automation_ingest_url  # noqa: PLC0415
                    except Exception as exc:  # noqa: BLE001
                        failures.append(f"web_automation_import_failed:{source_url}:{exc}")
                        continue
                    fetch = _web_automation_ingest_url(
                        url=str(source_url),
                        ingest_batch_id=str(job["ingest_batch_id"]),
                        run_id=None,
                    )
                    if not fetch.get("ok"):
                        failures.append(f"web_fetch_failed:{source_url}:{fetch.get('error')}")
                        continue
                    filename = _ensure_filename(fetch.get("filename") or entry.get("title"))
                    input_docs.append(
                        {
                            "file_bytes": fetch.get("bytes"),
                            "filename": filename,
                            "metadata": {**metadata, "limitations_text": fetch.get("limitations_text")},
                            "raw_source_uri": fetch.get("final_url") or source_url,
                            "raw_content_type": fetch.get("content_type"),
                            "source_url": fetch.get("final_url") or source_url,
                        }
                    )
                    continue
                failures.append("missing_path_or_url")

    if not docs and not input_docs:
        return {"status": "error", "error": "No documents found for this job.", "failures": failures}

    run_id = create_ingest_run(
        ingest_batch_id=str(job["ingest_batch_id"]),
        authority_id=str(job["authority_id"]) if job.get("authority_id") is not None else None,
        plan_cycle_id=job.get("plan_cycle_id"),
        inputs={
            "job_id": job_id,
            "rescue": True,
            "graph": "v4_freight_train",
        },
    )

    checkpointer = MemorySaver()
    queue_mode = os.environ.get("TPA_INGEST_QUEUE_MODE", "").lower()
    graph_mode = "cpu_only" if queue_mode == "separated" else "full"
    graph = build_ingestion_graph(checkpointer, mode=graph_mode)

    processed = 0
    skipped: list[str] = []

    active_docs = docs if docs else input_docs
    for idx, doc in enumerate(active_docs, start=1):
        if docs:
            blob_path = doc.get("raw_blob_path")
            if not blob_path:
                skipped.append(str(doc.get("id")))
                continue
            file_bytes, _, err = read_blob_bytes(blob_path)
            if err or not file_bytes:
                failures.append(f"{doc.get('id')}: {err}")
                continue
            filename = blob_path.split("/")[-1]
            doc_metadata = doc.get("metadata") or {}
            source_url = doc.get("raw_source_uri")
            content_type = doc.get("raw_content_type")
            thread_id = str(doc.get("id") or idx)
            authority_id = str(doc.get("authority_id") or job.get("authority_id"))
            plan_cycle_id = doc.get("plan_cycle_id") or job.get("plan_cycle_id")
        else:
            file_bytes = doc.get("file_bytes")
            if not file_bytes:
                failures.append(f"empty_payload:{doc.get('filename') or idx}")
                continue
            filename = doc.get("filename") or f"document-{idx}.pdf"
            doc_metadata = doc.get("metadata") or {}
            source_url = doc.get("source_url") or doc.get("raw_source_uri")
            content_type = doc.get("raw_content_type")
            thread_id = str(idx)
            authority_id = str(job.get("authority_id"))
            plan_cycle_id = job.get("plan_cycle_id")

        initial_state = {
            "run_id": run_id,
            "ingest_job_id": job_id,
            "ingest_batch_id": str(job["ingest_batch_id"]),
            "authority_id": authority_id,
            "plan_cycle_id": plan_cycle_id,
            "filename": filename,
            "file_bytes": file_bytes,
            "doc_metadata": doc_metadata,
            "source_url": source_url,
            "content_type": content_type,
            "counts": {},
            "steps_completed": [],
            "errors": [],
        }

        config = {"configurable": {"thread_id": thread_id}}
        final_state = await graph.ainvoke(initial_state, config)
        if isinstance(final_state, dict) and final_state.get("error"):
            failures.append(f"{thread_id}: {final_state.get('error')}")
            continue
        processed += 1

    if queue_mode == "separated" and not failures and not skipped:
        from celery import chain  # noqa: PLC0415
        from tpa_api.ingestion.tasks import run_vlm_stage, run_llm_stage, run_embeddings_stage  # noqa: PLC0415

        # Serialize GPU-bound stages to avoid VRAM contention across VLM/LLM/embeddings.
        chain(
            run_vlm_stage.si(run_id),
            run_llm_stage.si(run_id),
            run_embeddings_stage.si(run_id),
        ).apply_async()

    status = "ok"
    if failures or skipped:
        status = "error"
    return {
        "status": status,
        "run_id": run_id,
        "documents_processed": processed,
        "documents_skipped": skipped,
        "failures": failures,
    }


def run_graph_for_job_sync(job_id: str) -> dict[str, object]:
    return asyncio.run(run_graph_for_job(job_id))


async def main():
    if len(sys.argv) < 2:
        print("Usage: python run_graph.py <job_id>")
        return

    job_id = sys.argv[1]
    result = await run_graph_for_job(job_id)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
