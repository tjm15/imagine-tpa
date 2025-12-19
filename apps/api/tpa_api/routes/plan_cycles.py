from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from psycopg import errors as pg_errors

from ..api_utils import validate_uuid_or_400
from ..audit import _audit_event
from ..db import _db_execute, _db_execute_returning, _db_fetch_all, _db_fetch_one
from ..plan_cycles import _normalize_plan_cycle_status, _plan_cycle_conflict_statuses
from ..time_utils import _utc_now


router = APIRouter(tags=["plan-cycles"])


class PlanCycleCreate(BaseModel):
    authority_id: str
    plan_name: str
    status: str
    weight_hint: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    supersede_existing: bool = Field(
        default=False,
        description="If true, deactivate any conflicting active plan cycle(s) for this authority (sets is_active=false and superseded_by_cycle_id).",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/plan-cycles")
def create_plan_cycle(body: PlanCycleCreate) -> JSONResponse:
    now = _utc_now()
    authority_id = (body.authority_id or "").strip()
    if not authority_id:
        raise HTTPException(status_code=400, detail="authority_id must not be empty")

    plan_name = (body.plan_name or "").strip() or "Plan cycle"
    status = _normalize_plan_cycle_status(body.status)
    weight_hint = (body.weight_hint or "").strip().lower() if isinstance(body.weight_hint, str) and body.weight_hint.strip() else None

    conflict_statuses = _plan_cycle_conflict_statuses(status)
    conflicts: list[dict[str, Any]] = []
    if conflict_statuses:
        placeholders = ",".join(["%s"] * len(conflict_statuses))
        conflicts = _db_fetch_all(
            f"""
            SELECT id, status, plan_name
            FROM plan_cycles
            WHERE authority_id = %s
              AND is_active = true
              AND status IN ({placeholders})
            """,
            tuple([authority_id, *conflict_statuses]),
        )

    if conflicts and not body.supersede_existing:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Conflicting active plan cycle(s) exist for authority_id '{authority_id}' with statuses {set(conflict_statuses or [])}. "
                "Either provide supersede_existing=true or patch the existing cycle(s) to is_active=false."
            ),
        )

    if conflicts and body.supersede_existing:
        superseder_id = str(uuid4())
        # Deactivate existing conflicting cycles before inserting the new one.
        for c in conflicts:
            _db_execute(
                """
                UPDATE plan_cycles
                SET is_active = false, superseded_by_cycle_id = %s::uuid, updated_at = %s
                WHERE id = %s::uuid
                """,
                (superseder_id, now, str(c["id"])),
            )

    try:
        row = _db_execute_returning(
            """
            INSERT INTO plan_cycles (
              id, authority_id, plan_name, status, weight_hint, effective_from, effective_to,
              metadata_jsonb, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING id, authority_id, plan_name, status, weight_hint, effective_from, effective_to,
              superseded_by_cycle_id, is_active, metadata_jsonb, created_at, updated_at
            """,
            (
                str(uuid4()),
                authority_id,
                plan_name,
                status,
                weight_hint,
                body.effective_from,
                body.effective_to,
                json.dumps(body.metadata, ensure_ascii=False),
                now,
                now,
            ),
        )
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Conflicting active plan cycle exists for this authority/status group.") from exc

    _audit_event(
        event_type="plan_cycle_created",
        payload={"plan_cycle_id": str(row["id"]), "authority_id": authority_id, "status": row["status"]},
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "plan_cycle_id": str(row["id"]),
                "authority_id": row["authority_id"],
                "plan_name": row["plan_name"],
                "status": row["status"],
                "weight_hint": row["weight_hint"],
                "effective_from": row["effective_from"],
                "effective_to": row["effective_to"],
                "superseded_by_cycle_id": row["superseded_by_cycle_id"],
                "is_active": row["is_active"],
                "metadata": row["metadata_jsonb"] or {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    )


class PlanCyclePatch(BaseModel):
    status: str | None = None
    weight_hint: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    superseded_by_cycle_id: str | None = None
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


@router.patch("/plan-cycles/{plan_cycle_id}")
def patch_plan_cycle(plan_cycle_id: str, body: PlanCyclePatch) -> JSONResponse:
    plan_cycle_id = validate_uuid_or_400(plan_cycle_id, field_name="plan_cycle_id")
    existing = _db_fetch_one(
        "SELECT id, authority_id, status, is_active FROM plan_cycles WHERE id = %s::uuid",
        (plan_cycle_id,),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="plan_cycle_id not found")

    next_status = (
        _normalize_plan_cycle_status(body.status)
        if body.status is not None
        else _normalize_plan_cycle_status(existing["status"])
    )
    next_is_active = bool(body.is_active) if body.is_active is not None else bool(existing["is_active"])
    conflict_statuses = _plan_cycle_conflict_statuses(next_status)
    if next_is_active and conflict_statuses:
        placeholders = ",".join(["%s"] * len(conflict_statuses))
        conflict = _db_fetch_one(
            f"""
            SELECT id
            FROM plan_cycles
            WHERE authority_id = %s
              AND is_active = true
              AND status IN ({placeholders})
              AND id <> %s::uuid
            LIMIT 1
            """,
            tuple([existing["authority_id"], *conflict_statuses, plan_cycle_id]),
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot activate/set status to {set(conflict_statuses)}: another active plan cycle exists ({str(conflict['id'])}). "
                    "Deactivate/supersede it first."
                ),
            )

    now = _utc_now()
    try:
        row = _db_execute_returning(
            """
            UPDATE plan_cycles
            SET
              status = COALESCE(%s, status),
              weight_hint = COALESCE(%s, weight_hint),
              effective_from = COALESCE(%s, effective_from),
              effective_to = COALESCE(%s, effective_to),
              superseded_by_cycle_id = COALESCE(%s::uuid, superseded_by_cycle_id),
              is_active = COALESCE(%s, is_active),
              metadata_jsonb = COALESCE(%s::jsonb, metadata_jsonb),
              updated_at = %s
            WHERE id = %s::uuid
            RETURNING
              id, authority_id, plan_name, status, weight_hint, effective_from, effective_to,
              superseded_by_cycle_id, is_active, metadata_jsonb, created_at, updated_at
            """,
            (
                body.status,
                body.weight_hint,
                body.effective_from,
                body.effective_to,
                body.superseded_by_cycle_id,
                body.is_active,
                json.dumps(body.metadata, ensure_ascii=False) if body.metadata is not None else None,
                now,
                plan_cycle_id,
            ),
        )
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Conflicting active plan cycle exists for this authority/status group.") from exc

    _audit_event(
        event_type="plan_cycle_updated",
        payload={"plan_cycle_id": str(row["id"]), "changes": jsonable_encoder(body)},
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "plan_cycle_id": str(row["id"]),
                "authority_id": row["authority_id"],
                "plan_name": row["plan_name"],
                "status": row["status"],
                "weight_hint": row["weight_hint"],
                "effective_from": row["effective_from"],
                "effective_to": row["effective_to"],
                "superseded_by_cycle_id": row["superseded_by_cycle_id"],
                "is_active": row["is_active"],
                "metadata": row["metadata_jsonb"] or {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    )


@router.get("/plan-cycles")
def list_plan_cycles(authority_id: str | None = None, active_only: bool = True) -> JSONResponse:
    where: list[str] = []
    params: list[Any] = []
    if authority_id:
        where.append("authority_id = %s")
        params.append(authority_id)
    if active_only:
        where.append("is_active = true")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = _db_fetch_all(
        f"""
        SELECT
          id, authority_id, plan_name, status, weight_hint, effective_from, effective_to,
          superseded_by_cycle_id, is_active, metadata_jsonb, created_at, updated_at
        FROM plan_cycles
        {where_sql}
        ORDER BY updated_at DESC
        """,
        tuple(params),
    )
    items = [
        {
            "plan_cycle_id": str(r["id"]),
            "authority_id": r["authority_id"],
            "plan_name": r["plan_name"],
            "status": r["status"],
            "weight_hint": r["weight_hint"],
            "effective_from": r["effective_from"],
            "effective_to": r["effective_to"],
            "superseded_by_cycle_id": r["superseded_by_cycle_id"],
            "is_active": r["is_active"],
            "metadata": r["metadata_jsonb"] or {},
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"plan_cycles": items}))

