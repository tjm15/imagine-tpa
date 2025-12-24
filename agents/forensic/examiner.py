import os
import sys
import time
import json
import psycopg
from psycopg.rows import dict_row
import boto3
from botocore.client import Config

# Add project root
sys.path.append(os.getcwd())

# Configuration (from env or defaults matching compose.oss.yml)
DB_DSN = os.environ.get("TPA_DB_DSN", "postgresql://tpa:tpa@localhost:5432/tpa")
S3_ENDPOINT = os.environ.get("TPA_S3_ENDPOINT", "http://localhost:9000")
S3_ACCESS_KEY = os.environ.get("TPA_S3_ACCESS_KEY", "tpa")
S3_SECRET_KEY = os.environ.get("TPA_S3_SECRET_KEY", "change-me")
S3_BUCKET = os.environ.get("TPA_S3_BUCKET", "tpa")

class Examiner:
    def __init__(self):
        self.conn = psycopg.connect(DB_DSN, row_factory=dict_row)
        self.s3 = boto3.client('s3',
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            config=Config(signature_version='s3v4'),
            region_name='us-east-1' # dummy
        )

    def get_ingest_job(self, job_id):
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM ingest_runs WHERE run_id = %s", (job_id,))
            return cur.fetchone()

    def get_run_id_for_job(self, job_id):
        with self.conn.cursor() as cur:
            cur.execute("SELECT id FROM ingest_runs WHERE ingest_batch_id = (SELECT ingest_batch_id FROM ingest_jobs WHERE id = %s)", (job_id,))
            res = cur.fetchone()
            return res['id'] if res else None

    def get_run_steps(self, run_id):
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM ingest_run_steps 
                WHERE run_id = %s 
                ORDER BY started_at ASC
            """, (run_id,))
            return cur.fetchall()

    def trace(self, job_id, watch=False):
        print(f"🕵️  Tracing Job: {job_id}")
        run_id = self.get_run_id_for_job(job_id)
        
        while not run_id:
            print("⏳ Waiting for Run to be initialized...")
            time.sleep(2)
            run_id = self.get_run_id_for_job(job_id)

        print(f"🏃 Found Run: {run_id}")
        seen_steps = set()
        
        while True:
            steps = self.get_run_steps(run_id)
            for step in steps:
                if step['id'] not in seen_steps:
                    status_icon = "✅" if step['status'] == 'completed' else "❌" if step['status'] == 'failed' else "⏳"
                    print(f"{status_icon} [{step['step_name']}] {step['error_text'] or ''}")
                    seen_steps.add(step['id'])
            
            # Check top level run status
            with self.conn.cursor() as cur:
                cur.execute("SELECT status FROM ingest_runs WHERE id = %s", (run_id,))
                run = cur.fetchone()
            
            if run and run['status'] in ('completed', 'failed'):
                print(f"\n🏁 Run Finished: {run['status']}")
                break
            
            if not watch:
                break
            time.sleep(2)

    def dump_stage_artifacts(self, job_id, stage_name, output_dir):
        """
        Dumps artifacts associated with a stage to a local directory for inspection.
        """
        os.makedirs(output_dir, exist_ok=True)
        print(f"📦 Dumping artifacts for '{stage_name}' to {output_dir}...")
        
        run_id = self.get_run_id_for_job(job_id)
        if not run_id:
            print("Run not found")
            return

        with self.conn.cursor() as cur:
            if stage_name == 'canonical_load':
                # Dump chunks
                cur.execute("SELECT * FROM chunks WHERE run_id = %s LIMIT 50", (run_id,))
                chunks = cur.fetchall()
                with open(f"{output_dir}/chunks.json", "w") as f:
                    json.dump(chunks, f, default=str, indent=2)
                print(f"  -> Saved {len(chunks)} chunks")

            elif stage_name == 'structural_llm':
                # Dump extracted policies
                cur.execute("SELECT * FROM policy_clauses WHERE run_id = %s", (run_id,))
                clauses = cur.fetchall()
                with open(f"{output_dir}/clauses.json", "w") as f:
                    json.dump(clauses, f, default=str, indent=2)
                print(f"  -> Saved {len(clauses)} clauses")

    def diagnose(self, job_id):
        run_id = self.get_run_id_for_job(job_id)
        if not run_id:
            print(json.dumps({"error": "run_not_found"}))
            return

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT step_name, started_at, status 
                FROM ingest_run_steps 
                WHERE run_id = %s AND status = 'running'
                ORDER BY started_at ASC
                LIMIT 1
            """, (run_id,))
            step = cur.fetchone()
        
        if not step:
            print(json.dumps({"status": "no_running_steps"}))
            return

        service_map = {
            "anchor_raw": "tpa-api",
            "docling_parse": "tpa-docparse",
            "canonical_load": "tpa-api",
            "document_identity_status": "tpa-llm",
            "visual_semantics_asset": "tpa-vlm",
            "visual_segmentation": "tpa-sam2-segmentation", 
            "visual_vectorization": "tpa-vectorization-worker",
            "visual_semantics_regions": "tpa-vlm",
            "visual_georef": "tpa-georef-agent",
            "visual_linking": "tpa-llm",
            "visual_embeddings": "tpa-embeddings",
            "visual_assertion_embeddings": "tpa-embeddings",
            "structural_llm": "tpa-llm",
            "edges_llm": "tpa-llm",
            "embeddings": "tpa-embeddings"
        }

        service = service_map.get(step['step_name'], "tpa-api")
        
        print(json.dumps({
            "step_name": step['step_name'],
            "started_at": step['started_at'].isoformat() if step['started_at'] else None,
            "service": service
        }))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python agents/forensic/examiner.py <command> [args]")
        sys.exit(1)
        
    cmd = sys.argv[1]
    examiner = Examiner()
    
    if cmd == "trace":
        examiner.trace(sys.argv[2], watch=True)
    elif cmd == "dump":
        examiner.dump_stage_artifacts(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "diagnose":
        examiner.diagnose(sys.argv[2])
    else:
        print("Unknown command")
