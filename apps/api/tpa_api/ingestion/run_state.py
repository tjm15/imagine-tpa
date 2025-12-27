from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

from tpa_api.db import _db_execute, _db_fetch_one
from tpa_api.time_utils import _utc_now


def create_ingest_run(
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


def load_ingest_job(job_id: str) -> dict[str, Any] | None:
    return _db_fetch_one("SELECT * FROM ingest_jobs WHERE id = %s::uuid", (job_id,))


def load_ingest_run_context(run_id: str) -> dict[str, Any]:
    row = _db_fetch_one(
        """
        SELECT id, ingest_batch_id, authority_id, plan_cycle_id
        FROM ingest_runs
        WHERE id = %s::uuid
        """,
        (run_id,),
    )
    if not isinstance(row, dict):
        raise RuntimeError("ingest_run_not_found")
    return row
