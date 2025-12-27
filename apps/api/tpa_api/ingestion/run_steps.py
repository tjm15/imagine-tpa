from __future__ import annotations

import json
from typing import Any

from tpa_api.db import _db_execute


def _update_run_step_progress(
    *,
    run_id: str,
    step_name: str,
    outputs: dict[str, Any],
    status: str = "running",
    error_text: str | None = None,
) -> None:
    try:
        _db_execute(
            """
            UPDATE ingest_run_steps
            SET status = %s,
                outputs_jsonb = outputs_jsonb || %s::jsonb,
                error_text = COALESCE(error_text, %s)
            WHERE run_id = %s::uuid AND step_name = %s
            """,
            (
                status,
                json.dumps(outputs, ensure_ascii=False),
                error_text,
                run_id,
                step_name,
            ),
        )
    except Exception:  # noqa: BLE001
        pass
