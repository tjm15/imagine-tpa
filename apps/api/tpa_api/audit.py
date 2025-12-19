from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from .db import _db_execute
from .time_utils import _utc_now


def _audit_event(
    *,
    event_type: str,
    actor_type: str = "user",
    actor_id: str | None = None,
    run_id: str | None = None,
    plan_project_id: str | None = None,
    culp_stage_id: str | None = None,
    scenario_id: str | None = None,
    tool_run_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    _db_execute(
        """
        INSERT INTO audit_events (
          id, timestamp, event_type, actor_type, actor_id, run_id, plan_project_id,
          culp_stage_id, scenario_id, tool_run_id, payload_jsonb
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            str(uuid4()),
            _utc_now(),
            event_type,
            actor_type,
            actor_id,
            run_id,
            plan_project_id,
            culp_stage_id,
            scenario_id,
            tool_run_id,
            json.dumps(payload or {}, ensure_ascii=False),
        ),
    )

