import sys
import os
import asyncio
from pathlib import Path
from uuid import uuid4

# Add repo root to path
sys.path.append(str(Path(__file__).parent.parent))

from tpa_api.ingest_worker import process_ingest_job
from tpa_api.services.ingest import _create_ingest_job, _enqueue_ingest_job
from tpa_api.db import init_db_pool, _db_execute

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug_ingest_file.py <path_to_pdf>")
        sys.exit(1)

    file_path = Path(sys.argv[1]).resolve()
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    print(f"--- Debug Ingest: {file_path.name} ---")

    # 1. Setup Env (Mock if needed, but assuming .env is loaded or env vars present)
    # We assume the script is run in an environment where TPA_DB_DSN etc are set.
    # If running locally, you might need `source .env` first.

    init_db_pool()

    # 2. Copy file to authority_packs/debug (simulating the upload)
    pack_root = Path(os.environ.get("TPA_AUTHORITY_PACKS_ROOT", "authority_packs")).resolve()
    debug_dir = pack_root / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    target_path = debug_dir / file_path.name
    target_path.write_bytes(file_path.read_bytes())
    print(f"Copied to {target_path}")

    # 3. Create Job (Synchronously)
    authority_id = "debug"
    ingest_batch_id = str(uuid4())
    
    print(f"Creating Batch {ingest_batch_id}...")
    _db_execute(
        """
        INSERT INTO ingest_batches (
          id, source_system, authority_id, status, started_at, inputs_jsonb, outputs_jsonb
        )
        VALUES (%s, %s, %s, %s, NOW(), %s::jsonb, %s::jsonb)
        """,
        (ingest_batch_id, "debug_script", authority_id, "running", "{}", "{}"),
    )

    print("Creating Job...")
    ingest_job_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO ingest_jobs (
          id, ingest_batch_id, authority_id, job_type, status, inputs_jsonb, outputs_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s, %s::jsonb, %s::jsonb, NOW())
        """,
        (
            ingest_job_id,
            ingest_batch_id,
            authority_id,
            "manual_upload",
            "pending",
            json_dumps({
                "authority_id": authority_id,
                "pack_dir": str(debug_dir),
                "documents": [
                    {
                        "file_path": file_path.name,
                        "title": file_path.name,
                        "source": "debug_script",
                    }
                ],
            }),
            "{}",
        ),
    )

    print(f"Job ID: {ingest_job_id}")
    print(">>> STARTING WORKER PROCESS (Foreground) <<<")
    
    try:
        result = process_ingest_job(ingest_job_id)
        print("\n--- Result ---")
        print(json_dumps(result, indent=2))
    except Exception as e:
        print(f"\n!!! FATAL ERROR !!!")
        print(e)
        import traceback
        traceback.print_exc()

def json_dumps(obj, indent=None):
    import json
    return json.dumps(obj, ensure_ascii=False, indent=indent, default=str)

if __name__ == "__main__":
    main()
