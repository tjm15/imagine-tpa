import sys
import asyncio
import uuid
from tpa_api.ingestion.ingestion_graph import build_ingestion_graph
from tpa_api.db import init_db_pool, _db_fetch_one
from tpa_api.blob_store import read_blob_bytes
from langgraph.checkpoint.memory import MemorySaver

async def main():
    if len(sys.argv) < 2:
        print("Usage: python run_graph.py <job_id>")
        return

    job_id = sys.argv[1]
    init_db_pool()
    
    # 1. Load Job & Document info
    job = _db_fetch_one("SELECT * FROM ingest_jobs WHERE id = %s::uuid", (job_id,))
    if not job:
        print(f"Job {job_id} not found.")
        return

    # Find the document created by this job (or batch)
    # The legacy worker creates document row in 'anchor_raw' step.
    # If we are rescuing a job that failed AFTER anchor_raw, document row exists.
    
    doc = _db_fetch_one("""
        SELECT * FROM documents 
        WHERE ingest_batch_id = %s::uuid 
        LIMIT 1
    """, (str(job['ingest_batch_id']),))
    
    if not doc:
        print("Document not found for this job. Ensure 'anchor_raw' ran.")
        return

    print(f"Processing Document: {doc['id']} ({doc['raw_blob_path']})")
    
    # 2. Fetch Bytes
    file_bytes, _, err = read_blob_bytes(doc['raw_blob_path'])
    if err or not file_bytes:
        print(f"Failed to read blob: {err}")
        return

    # 3. Create Run Record
    from tpa_api.ingest_worker import _create_ingest_run
    
    run_id = _create_ingest_run(
        ingest_batch_id=str(job['ingest_batch_id']),
        authority_id=str(job['authority_id']),
        plan_cycle_id=str(job['plan_cycle_id']),
        inputs={
            "job_id": job_id,
            "rescue": True,
            "graph": "v4_freight_train"
        }
    )
    print(f"Created Run: {run_id}")

    # 4. Setup Graph
    checkpointer = MemorySaver()
    graph = build_ingestion_graph(checkpointer)
    
    initial_state = {
        "run_id": run_id,
        "ingest_job_id": job_id,
        "ingest_batch_id": str(job['ingest_batch_id']),
        "authority_id": str(job['authority_id']),
        "plan_cycle_id": str(job['plan_cycle_id']),
        "document_id": str(doc['id']),
        "filename": doc['raw_blob_path'].split('/')[-1],
        "file_bytes": file_bytes,
        "doc_metadata": doc.get('metadata') or {},
        "visual_queue": [],
        "text_queue": []
    }
    
    print("🚀 Starting Freight Train Graph...")
    config = {"configurable": {"thread_id": "1"}}
    
    async for event in graph.astream(initial_state, config):
        for key, value in event.items():
            print(f"✅ Node Finished: {key}")
            if key == "vlm_batch":
                print(f"   Processed {len(value.get('visual_queue', []))} visuals.")
            if key == "llm_batch":
                print(f"   Processed structures.")

if __name__ == "__main__":
    asyncio.run(main())