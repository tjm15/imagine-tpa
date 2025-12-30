from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from tpa_api.db import _db_execute, _db_fetch_one
from tpa_api.time_utils import _utc_now


_TERMINAL_STATUSES = {"success", "error", "skipped"}


def _update_run_step_progress(
    *,
    run_id: str,
    step_name: str,
    outputs: dict[str, Any],
    status: str = "running",
    error_text: str | None = None,
) -> None:
    now = _utc_now()
    ended_at = now if status in _TERMINAL_STATUSES else None
    try:
        existing = _db_fetch_one(
            """
            SELECT id
            FROM ingest_run_steps
            WHERE run_id = %s::uuid AND step_name = %s
            """,
            (run_id, step_name),
        )
        if not existing:
            batch_row = _db_fetch_one(
                "SELECT ingest_batch_id FROM ingest_runs WHERE id = %s::uuid",
                (run_id,),
            )
            ingest_batch_id = batch_row.get("ingest_batch_id") if batch_row else None
            _db_execute(
                """
                INSERT INTO ingest_run_steps (
                  id, ingest_batch_id, run_id, step_name, status,
                  started_at, ended_at, inputs_jsonb, outputs_jsonb, error_text
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                """,
                (
                    str(uuid4()),
                    ingest_batch_id,
                    run_id,
                    step_name,
                    status,
                    now,
                    ended_at,
                    json.dumps({}, ensure_ascii=False),
                    json.dumps(outputs, ensure_ascii=False),
                    error_text,
                ),
            )
        else:
            _db_execute(
                """
                UPDATE ingest_run_steps
                SET status = %s,
                    outputs_jsonb = outputs_jsonb || %s::jsonb,
                    error_text = COALESCE(error_text, %s),
                    ended_at = COALESCE(ended_at, %s)
                WHERE run_id = %s::uuid AND step_name = %s
                """,
                (
                    status,
                    json.dumps(outputs, ensure_ascii=False),
                    error_text,
                    ended_at,
                    run_id,
                    step_name,
                ),
            )
    except Exception:  # noqa: BLE001
        pass
