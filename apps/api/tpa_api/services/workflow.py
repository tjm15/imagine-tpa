from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..db import _db_execute, _db_fetch_all, _db_fetch_one
from ..time_utils import _utc_now
from .culp_artefacts import ensure_culp_artefacts


def _get_rule_pack_version(rule_pack_version_id: str) -> dict[str, Any]:
    row = _db_fetch_one(
        """
        SELECT id, rule_pack_id, version, content_jsonb
        FROM rule_pack_versions
        WHERE id = %s::uuid
        """,
        (rule_pack_version_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Rule pack version not found")
    content = row.get("content_jsonb") or {}
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            content = {}
    return {
        "rule_pack_version_id": str(row["id"]),
        "rule_pack_id": str(row["rule_pack_id"]),
        "version": row["version"],
        "content": content,
    }


def _get_current_workflow(plan_project_id: str) -> dict[str, Any] | None:
    row = _db_fetch_one(
        """
        SELECT id, plan_project_id, rule_pack_version_id, state_id, state_started_at, state_updated_at, metadata_jsonb
        FROM plan_workflow_states
        WHERE plan_project_id = %s::uuid
        """,
        (plan_project_id,),
    )
    if not row:
        return None
    return {
        "workflow_state_id": str(row["id"]),
        "plan_project_id": str(row["plan_project_id"]),
        "rule_pack_version_id": str(row["rule_pack_version_id"]),
        "state_id": row["state_id"],
        "state_started_at": row["state_started_at"],
        "state_updated_at": row["state_updated_at"],
        "metadata": row.get("metadata_jsonb") or {},
    }


def _get_lifecycle_states(pack_content: dict[str, Any]) -> list[dict[str, Any]]:
    states = pack_content.get("lifecycle_states")
    if not isinstance(states, list):
        return []
    return [s for s in states if isinstance(s, dict) and s.get("id")]


def _get_transitions(pack_content: dict[str, Any]) -> list[dict[str, Any]]:
    transitions = pack_content.get("transitions")
    if not isinstance(transitions, list):
        return []
    return [t for t in transitions if isinstance(t, dict) and t.get("from") and t.get("to")]


def _culp_stage_for_state(pack_content: dict[str, Any], state_id: str) -> str | None:
    for state in _get_lifecycle_states(pack_content):
        if state.get("id") == state_id:
            return state.get("culp_stage_id")
    return None


def init_plan_workflow(plan_project_id: str, rule_pack_version_id: str) -> JSONResponse:
    existing = _get_current_workflow(plan_project_id)
    if existing:
        return JSONResponse(content=jsonable_encoder(existing))

    pack = _get_rule_pack_version(rule_pack_version_id)
    pack_content = pack["content"]
    lifecycle_states = _get_lifecycle_states(pack_content)
    if not lifecycle_states:
        raise HTTPException(status_code=400, detail="Rule pack has no lifecycle states")
    initial_state = lifecycle_states[0]["id"]
    now = _utc_now()

    row = _db_execute_returning(
        """
        INSERT INTO plan_workflow_states (
          id, plan_project_id, rule_pack_version_id, state_id,
          state_started_at, state_updated_at, metadata_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s::jsonb, %s)
        RETURNING id
        """,
        (
            str(uuid4()),
            plan_project_id,
            rule_pack_version_id,
            initial_state,
            now,
            now,
            json.dumps({}, ensure_ascii=False),
            now,
        ),
    )
    ensure_culp_artefacts(plan_project_id, pack_content.get("process_model_id"))
    _db_execute(
        "UPDATE plan_projects SET status = %s, current_stage_id = %s, updated_at = %s WHERE id = %s::uuid",
        (
            initial_state,
            _culp_stage_for_state(pack_content, initial_state),
            now,
            plan_project_id,
        ),
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "workflow_state_id": str(row["id"]),
                "plan_project_id": plan_project_id,
                "rule_pack_version_id": rule_pack_version_id,
                "state_id": initial_state,
                "state_started_at": now,
                "state_updated_at": now,
            }
        )
    )


def _check_artefacts_published(plan_project_id: str, artefact_keys: list[str]) -> tuple[bool, str]:
    if not artefact_keys:
        return True, "no_artefacts_required"
    rows = _db_fetch_all(
        """
        SELECT artefact_key, status
        FROM culp_artefacts
        WHERE plan_project_id = %s::uuid AND artefact_key = ANY(%s)
        """,
        (plan_project_id, artefact_keys),
    )
    status_by_key = {r["artefact_key"]: r["status"] for r in rows}
    missing = [k for k in artefact_keys if status_by_key.get(k) != "published"]
    if missing:
        return False, f"unpublished_artefacts:{','.join(missing)}"
    return True, "ok"


def _check_timetable_published(plan_project_id: str) -> tuple[bool, str]:
    row = _db_fetch_one(
        "SELECT id FROM timetables WHERE plan_project_id = %s::uuid AND status = 'published'",
        (plan_project_id,),
    )
    return (row is not None), ("ok" if row else "timetable_not_published")


def _check_consultation_status(plan_project_id: str, consultation_type: str, status: str) -> tuple[bool, str]:
    row = _db_fetch_one(
        """
        SELECT id FROM consultations
        WHERE plan_project_id = %s::uuid AND consultation_type = %s AND status = %s
        """,
        (plan_project_id, consultation_type, status),
    )
    return (row is not None), ("ok" if row else f"consultation_status_missing:{consultation_type}:{status}")


def _check_consultation_summary(plan_project_id: str, consultation_type: str) -> tuple[bool, str]:
    row = _db_fetch_one(
        """
        SELECT s.id
        FROM consultations c
        JOIN consultation_summaries s ON s.consultation_id = c.id
        WHERE c.plan_project_id = %s::uuid
          AND c.consultation_type = %s
          AND s.status = 'published'
        """,
        (plan_project_id, consultation_type),
    )
    return (row is not None), ("ok" if row else f"consultation_summary_missing:{consultation_type}")


def _check_consultation_min_duration(plan_project_id: str, consultation_type: str, min_days: int) -> tuple[bool, str]:
    row = _db_fetch_one(
        """
        SELECT open_at, close_at
        FROM consultations
        WHERE plan_project_id = %s::uuid AND consultation_type = %s AND status = 'closed'
        ORDER BY close_at DESC
        LIMIT 1
        """,
        (plan_project_id, consultation_type),
    )
    if not row or not row.get("open_at") or not row.get("close_at"):
        return False, f"consultation_window_missing:{consultation_type}"
    delta = row["close_at"] - row["open_at"]
    if delta < timedelta(days=min_days):
        return False, f"consultation_too_short:{consultation_type}:{delta.days}d"
    return True, "ok"


def _check_min_days_between_states(plan_project_id: str, from_state_id: str, min_days: int) -> tuple[bool, str]:
    row = _db_fetch_one(
        """
        SELECT transitioned_at
        FROM workflow_transitions
        WHERE plan_project_id = %s::uuid AND to_state_id = %s
        ORDER BY transitioned_at DESC
        LIMIT 1
        """,
        (plan_project_id, from_state_id),
    )
    if not row or not row.get("transitioned_at"):
        return False, f"state_transition_missing:{from_state_id}"
    elapsed = _utc_now() - row["transitioned_at"]
    if elapsed < timedelta(days=min_days):
        return False, f"min_days_not_met:{from_state_id}:{elapsed.days}d"
    return True, "ok"


def _check_max_days_in_state(current_state: dict[str, Any], state_id: str, max_days: int) -> tuple[bool, str]:
    if current_state.get("state_id") != state_id:
        return True, "not_applicable"
    started_at = current_state.get("state_started_at")
    if not isinstance(started_at, datetime):
        return False, "state_started_at_missing"
    elapsed = _utc_now() - started_at
    if elapsed > timedelta(days=max_days):
        return False, f"state_exceeds_max_days:{state_id}:{elapsed.days}d"
    return True, "ok"


def _check_gateway_outcome(plan_project_id: str, gateway_type: str) -> tuple[bool, str]:
    row = _db_fetch_one(
        """
        SELECT o.id
        FROM gateway_submissions s
        JOIN gateway_outcomes o ON o.gateway_submission_id = s.id
        WHERE s.plan_project_id = %s::uuid AND s.gateway_type = %s AND o.published_at IS NOT NULL
        ORDER BY o.published_at DESC
        LIMIT 1
        """,
        (plan_project_id, gateway_type),
    )
    return (row is not None), ("ok" if row else f"gateway_outcome_missing:{gateway_type}")


def _evaluate_check(
    plan_project_id: str,
    current_state: dict[str, Any],
    check: dict[str, Any],
) -> tuple[bool, str]:
    check_type = check.get("type")
    params = check.get("params") or {}
    if check_type == "artefacts_published":
        keys = params.get("artefact_keys") or []
        return _check_artefacts_published(plan_project_id, keys)
    if check_type == "timetable_published":
        return _check_timetable_published(plan_project_id)
    if check_type == "consultation_status":
        return _check_consultation_status(
            plan_project_id,
            str(params.get("consultation_type") or ""),
            str(params.get("status") or ""),
        )
    if check_type == "consultation_summary_published":
        return _check_consultation_summary(plan_project_id, str(params.get("consultation_type") or ""))
    if check_type == "consultation_min_duration":
        min_days = int(params.get("min_days") or 0)
        return _check_consultation_min_duration(plan_project_id, str(params.get("consultation_type") or ""), min_days)
    if check_type == "min_days_between_states":
        min_days = int(params.get("min_days") or 0)
        from_state = str(params.get("from_state_id") or "")
        return _check_min_days_between_states(plan_project_id, from_state, min_days)
    if check_type == "max_days_in_state":
        max_days = int(params.get("max_days") or 0)
        state_id = str(params.get("state_id") or "")
        return _check_max_days_in_state(current_state, state_id, max_days)
    if check_type == "gateway_outcome_published":
        return _check_gateway_outcome(plan_project_id, str(params.get("gateway_type") or ""))
    return False, f"unknown_check:{check_type}"


def get_workflow_status(plan_project_id: str) -> JSONResponse:
    current_state = _get_current_workflow(plan_project_id)
    if not current_state:
        raise HTTPException(status_code=404, detail="Workflow not initialised")
    pack = _get_rule_pack_version(current_state["rule_pack_version_id"])
    pack_content = pack["content"]
    transitions = _get_transitions(pack_content)
    available: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for transition in transitions:
        if transition.get("from") != current_state["state_id"]:
            continue
        checks = transition.get("checks", [])
        results = []
        ok = True
        for check in checks:
            severity = str(check.get("severity") or "hard").lower()
            passed, detail = _evaluate_check(plan_project_id, current_state, check)
            results.append(
                {
                    "check_key": check.get("check_key"),
                    "type": check.get("type"),
                    "severity": severity,
                    "passed": passed,
                    "detail": detail,
                }
            )
            if not passed and severity != "warn":
                ok = False
        entry = {
            "to_state_id": transition.get("to"),
            "checks": results,
        }
        if ok:
            available.append(entry)
        else:
            blocked.append(entry)

    return JSONResponse(
        content=jsonable_encoder(
            {
                "current_state": current_state,
                "available_transitions": available,
                "blocked_transitions": blocked,
            }
        )
    )


def advance_workflow(plan_project_id: str, to_state_id: str, actor_type: str = "system") -> JSONResponse:
    current_state = _get_current_workflow(plan_project_id)
    if not current_state:
        raise HTTPException(status_code=404, detail="Workflow not initialised")
    pack = _get_rule_pack_version(current_state["rule_pack_version_id"])
    pack_content = pack["content"]
    transitions = _get_transitions(pack_content)
    candidate = None
    for transition in transitions:
        if transition.get("from") == current_state["state_id"] and transition.get("to") == to_state_id:
            candidate = transition
            break
    if not candidate:
        raise HTTPException(status_code=400, detail="Invalid transition for current state")

    checks = candidate.get("checks", [])
    failures = []
    for check in checks:
        severity = str(check.get("severity") or "hard").lower()
        passed, detail = _evaluate_check(plan_project_id, current_state, check)
        if not passed and severity != "warn":
            failures.append({"check_key": check.get("check_key"), "detail": detail})
    if failures:
        raise HTTPException(status_code=409, detail={"message": "Transition blocked", "failures": failures})

    now = _utc_now()
    _db_execute(
        """
        UPDATE plan_workflow_states
        SET state_id = %s, state_started_at = %s, state_updated_at = %s
        WHERE id = %s::uuid
        """,
        (to_state_id, now, now, current_state["workflow_state_id"]),
    )
    _db_execute(
        """
        INSERT INTO workflow_transitions (
          id, plan_project_id, rule_pack_version_id, from_state_id, to_state_id,
          transitioned_at, actor_type, metadata_jsonb
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            str(uuid4()),
            plan_project_id,
            current_state["rule_pack_version_id"],
            current_state["state_id"],
            to_state_id,
            now,
            actor_type,
            json.dumps({}, ensure_ascii=False),
        ),
    )
    _db_execute(
        "UPDATE plan_projects SET status = %s, current_stage_id = %s, updated_at = %s WHERE id = %s::uuid",
        (
            to_state_id,
            _culp_stage_for_state(pack_content, to_state_id),
            now,
            plan_project_id,
        ),
    )

    updated = _get_current_workflow(plan_project_id)
    return JSONResponse(content=jsonable_encoder({"current_state": updated}))
