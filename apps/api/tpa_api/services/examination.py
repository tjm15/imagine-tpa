from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import _db_execute_returning, _db_fetch_all
from ..time_utils import _utc_now


class ExaminationEventCreate(BaseModel):
    plan_project_id: str
    event_type: str
    event_date: str
    details: dict[str, Any] = Field(default_factory=dict)


class AdoptionStatementCreate(BaseModel):
    plan_project_id: str
    statement: dict[str, Any] = Field(default_factory=dict)
    publish: bool = Field(default=False)


def create_examination_event(body: ExaminationEventCreate) -> JSONResponse:
    row = _db_execute_returning(
        """
        INSERT INTO examination_events (
          id, plan_project_id, event_type, event_date, details_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
        RETURNING id, plan_project_id, event_type, event_date, details_jsonb, created_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            body.event_type,
            body.event_date,
            json.dumps(body.details, ensure_ascii=False),
            _utc_now(),
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_exam_event(row)))


def list_examination_events(plan_project_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, plan_project_id, event_type, event_date, details_jsonb, created_at
        FROM examination_events
        WHERE plan_project_id = %s::uuid
        ORDER BY event_date DESC
        """,
        (plan_project_id,),
    )
    items = [_row_to_exam_event(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"examination_events": items}))


def create_adoption_statement(body: AdoptionStatementCreate) -> JSONResponse:
    published_at = _utc_now() if body.publish else None
    row = _db_execute_returning(
        """
        INSERT INTO adoption_statements (
          id, plan_project_id, statement_jsonb, published_at, created_at
        )
        VALUES (%s, %s::uuid, %s::jsonb, %s, %s)
        RETURNING id, plan_project_id, statement_jsonb, published_at, created_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            json.dumps(body.statement, ensure_ascii=False),
            published_at,
            _utc_now(),
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_adoption(row)))


def list_adoption_statements(plan_project_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, plan_project_id, statement_jsonb, published_at, created_at
        FROM adoption_statements
        WHERE plan_project_id = %s::uuid
        ORDER BY created_at DESC
        """,
        (plan_project_id,),
    )
    items = [_row_to_adoption(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"adoption_statements": items}))


def _row_to_exam_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "examination_event_id": str(row["id"]),
        "plan_project_id": str(row["plan_project_id"]),
        "event_type": row["event_type"],
        "event_date": row["event_date"],
        "details": row.get("details_jsonb") or {},
        "created_at": row["created_at"],
    }


def _row_to_adoption(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "adoption_statement_id": str(row["id"]),
        "plan_project_id": str(row["plan_project_id"]),
        "statement": row.get("statement_jsonb") or {},
        "published_at": row.get("published_at"),
        "created_at": row["created_at"],
    }
