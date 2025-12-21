from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import _db_execute, _db_execute_returning, _db_fetch_all, _db_fetch_one
from ..time_utils import _utc_now


class GatewaySubmissionCreate(BaseModel):
    plan_project_id: str
    gateway_type: str
    status: str = Field(default="draft")
    submitted_at: str | None = None
    pack: dict[str, Any] = Field(default_factory=dict)


class GatewayOutcomeCreate(BaseModel):
    gateway_submission_id: str
    outcome: str
    findings: dict[str, Any] = Field(default_factory=dict)
    publish: bool = Field(default=False)


class StatementCreate(BaseModel):
    plan_project_id: str
    gateway_submission_id: str | None = None
    statement: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="draft")


def create_gateway_submission(body: GatewaySubmissionCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO gateway_submissions (
          id, plan_project_id, gateway_type, status, submitted_at, pack_jsonb, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s, %s::jsonb, %s, %s)
        RETURNING id, plan_project_id, gateway_type, status, submitted_at, pack_jsonb, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            body.gateway_type,
            body.status,
            body.submitted_at,
            json.dumps(body.pack, ensure_ascii=False),
            now,
            now,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_submission(row)))


def list_gateway_submissions(plan_project_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, plan_project_id, gateway_type, status, submitted_at, pack_jsonb, created_at, updated_at
        FROM gateway_submissions
        WHERE plan_project_id = %s::uuid
        ORDER BY updated_at DESC
        """,
        (plan_project_id,),
    )
    items = [_row_to_submission(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"gateway_submissions": items}))


def create_gateway_outcome(body: GatewayOutcomeCreate) -> JSONResponse:
    published_at = _utc_now() if body.publish else None
    row = _db_execute_returning(
        """
        INSERT INTO gateway_outcomes (
          id, gateway_submission_id, outcome, findings_jsonb, published_at, created_at
        )
        VALUES (%s, %s::uuid, %s, %s::jsonb, %s, %s)
        RETURNING id, gateway_submission_id, outcome, findings_jsonb, published_at, created_at
        """,
        (
            str(uuid4()),
            body.gateway_submission_id,
            body.outcome,
            json.dumps(body.findings, ensure_ascii=False),
            published_at,
            _utc_now(),
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_outcome(row)))


def list_gateway_outcomes(gateway_submission_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, gateway_submission_id, outcome, findings_jsonb, published_at, created_at
        FROM gateway_outcomes
        WHERE gateway_submission_id = %s::uuid
        ORDER BY created_at DESC
        """,
        (gateway_submission_id,),
    )
    items = [_row_to_outcome(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"gateway_outcomes": items}))


def create_statement_compliance(body: StatementCreate) -> JSONResponse:
    return _create_statement("statement_compliance", body)


def create_statement_soundness(body: StatementCreate) -> JSONResponse:
    return _create_statement("statement_soundness", body)


def create_readiness_for_exam(body: StatementCreate) -> JSONResponse:
    return _create_statement("readiness_for_exam", body)


def _create_statement(table: str, body: StatementCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        f"""
        INSERT INTO {table} (
          id, plan_project_id, gateway_submission_id, statement_jsonb, status, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s::jsonb, %s, %s, %s)
        RETURNING id, plan_project_id, gateway_submission_id, statement_jsonb, status, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            body.gateway_submission_id,
            json.dumps(body.statement, ensure_ascii=False),
            body.status,
            now,
            now,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_statement(row)))


def list_statements(table: str, plan_project_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        f"""
        SELECT id, plan_project_id, gateway_submission_id, statement_jsonb, status, created_at, updated_at
        FROM {table}
        WHERE plan_project_id = %s::uuid
        ORDER BY updated_at DESC
        """,
        (plan_project_id,),
    )
    items = [_row_to_statement(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"statements": items}))


def _row_to_submission(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "gateway_submission_id": str(row["id"]),
        "plan_project_id": str(row["plan_project_id"]),
        "gateway_type": row["gateway_type"],
        "status": row["status"],
        "submitted_at": row.get("submitted_at"),
        "pack": row.get("pack_jsonb") or {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_outcome(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "gateway_outcome_id": str(row["id"]),
        "gateway_submission_id": str(row["gateway_submission_id"]),
        "outcome": row["outcome"],
        "findings": row.get("findings_jsonb") or {},
        "published_at": row.get("published_at"),
        "created_at": row["created_at"],
    }


def _row_to_statement(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "statement_id": str(row["id"]),
        "plan_project_id": str(row["plan_project_id"]),
        "gateway_submission_id": (
            str(row["gateway_submission_id"]) if row.get("gateway_submission_id") else None
        ),
        "statement": row.get("statement_jsonb") or {},
        "status": row.get("status"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
