import os
import sys
import asyncio
from langgraph.checkpoint.memory import MemorySaver
from tpa_api.ingestion.ingestion_graph import build_ingestion_graph
from tpa_api.ingestion.run_state import create_ingest_run
from tpa_api.db import init_db_pool, _db_fetch_one, _db_fetch_all
from tpa_api.blob_store import read_blob_bytes


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
    if not docs:
        return {"status": "error", "error": "No documents found for this job."}

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
    failures: list[str] = []

    for idx, doc in enumerate(docs, start=1):
        blob_path = doc.get("raw_blob_path")
        if not blob_path:
            skipped.append(str(doc.get("id")))
            continue
        file_bytes, _, err = read_blob_bytes(blob_path)
        if err or not file_bytes:
            failures.append(f"{doc.get('id')}: {err}")
            continue

        initial_state = {
            "run_id": run_id,
            "ingest_job_id": job_id,
            "ingest_batch_id": str(job["ingest_batch_id"]),
            "authority_id": str(doc.get("authority_id") or job.get("authority_id")),
            "plan_cycle_id": doc.get("plan_cycle_id") or job.get("plan_cycle_id"),
            "filename": blob_path.split("/")[-1],
            "file_bytes": file_bytes,
            "doc_metadata": doc.get("metadata") or {},
            "source_url": doc.get("raw_source_uri"),
            "content_type": doc.get("raw_content_type"),
        }

        config = {"configurable": {"thread_id": str(doc.get("id") or idx)}}
        final_state = await graph.ainvoke(initial_state, config)
        if isinstance(final_state, dict) and final_state.get("error"):
            failures.append(f"{doc.get('id')}: {final_state.get('error')}")
            continue
        processed += 1

    if queue_mode == "separated" and not failures and not skipped:
        from tpa_api.ingestion.tasks import run_vlm_stage, run_llm_stage, run_embeddings_stage  # noqa: PLC0415

        run_vlm_stage.delay(run_id).get()
        run_llm_stage.delay(run_id).get()
        run_embeddings_stage.delay(run_id).get()

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
