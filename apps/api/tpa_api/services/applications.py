from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import _db_execute, _db_execute_returning, _db_fetch_all, _db_fetch_one
from ..time_utils import _utc_now


class ApplicationCreate(BaseModel):
    authority_id: str
    reference: str
    status: str = Field(default="new")
    received_at: str | None = None
    proposal_metadata: dict[str, Any] = Field(default_factory=dict)
    plan_project_id: str | None = None
    plan_cycle_id: str | None = None


class DecisionCreate(BaseModel):
    application_id: str
    outcome: str
    decision_date: str | None = None
    officer_report_document_id: str | None = None


def create_application(body: ApplicationCreate) -> JSONResponse:
    row = _db_execute_returning(
        """
        INSERT INTO applications (
          id, authority_id, reference, proposal_metadata, status, received_at, plan_project_id, plan_cycle_id
        )
        VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s::uuid, %s::uuid)
        RETURNING id, authority_id, reference, proposal_metadata, status, received_at, plan_project_id, plan_cycle_id
        """,
        (
            str(uuid4()),
            body.authority_id,
            body.reference,
            json.dumps(body.proposal_metadata, ensure_ascii=False),
            body.status,
            body.received_at,
            body.plan_project_id,
            body.plan_cycle_id,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_application(row)))


def list_applications(authority_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, authority_id, reference, proposal_metadata, status, received_at, plan_project_id, plan_cycle_id
        FROM applications
        WHERE authority_id = %s
        ORDER BY received_at DESC NULLS LAST
        """,
        (authority_id,),
    )
    items = [_row_to_application(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"applications": items}))


def create_decision(body: DecisionCreate) -> JSONResponse:
    app_row = _db_fetch_one(
        "SELECT id, authority_id, plan_project_id, plan_cycle_id FROM applications WHERE id = %s::uuid",
        (body.application_id,),
    )
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")
    row = _db_execute_returning(
        """
        INSERT INTO decisions (
          id, application_id, outcome, decision_date, officer_report_document_id
        )
        VALUES (%s, %s::uuid, %s, %s, %s::uuid)
        RETURNING id, application_id, outcome, decision_date, officer_report_document_id
        """,
        (
            str(uuid4()),
            body.application_id,
            body.outcome,
            body.decision_date,
            body.officer_report_document_id,
        ),
    )
    _emit_monitoring_event(app_row, body)
    return JSONResponse(content=jsonable_encoder(_row_to_decision(row)))


def list_decisions(application_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, application_id, outcome, decision_date, officer_report_document_id
        FROM decisions
        WHERE application_id = %s::uuid
        ORDER BY decision_date DESC NULLS LAST
        """,
        (application_id,),
    )
    items = [_row_to_decision(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"decisions": items}))


def _emit_monitoring_event(app_row: dict[str, Any], decision: DecisionCreate) -> None:
    payload = {
        "application_id": str(app_row["id"]),
        "plan_project_id": str(app_row["plan_project_id"]) if app_row.get("plan_project_id") else None,
        "plan_cycle_id": str(app_row["plan_cycle_id"]) if app_row.get("plan_cycle_id") else None,
        "outcome": decision.outcome,
        "decision_date": decision.decision_date,
    }
    _db_execute(
        """
        INSERT INTO monitoring_events (
          id, authority_id, event_type, event_date, payload_jsonb, provenance
        )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
        """,
        (
            str(uuid4()),
            app_row["authority_id"],
            "dm_decision",
            decision.decision_date or _utc_now().date().isoformat(),
            json.dumps(payload, ensure_ascii=False),
            json.dumps({"source": "dm_decision"}, ensure_ascii=False),
        ),
    )


def _row_to_application(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "application_id": str(row["id"]),
        "authority_id": row["authority_id"],
        "reference": row["reference"],
        "proposal_metadata": row.get("proposal_metadata") or {},
        "status": row["status"],
        "received_at": row.get("received_at"),
        "plan_project_id": str(row["plan_project_id"]) if row.get("plan_project_id") else None,
        "plan_cycle_id": str(row["plan_cycle_id"]) if row.get("plan_cycle_id") else None,
    }


def _row_to_decision(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_id": str(row["id"]),
        "application_id": str(row["application_id"]),
        "outcome": row["outcome"],
        "decision_date": row.get("decision_date"),
        "officer_report_document_id": (
            str(row["officer_report_document_id"]) if row.get("officer_report_document_id") else None
        ),
    }
