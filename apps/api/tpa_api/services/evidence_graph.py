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


class EvidenceItemCreate(BaseModel):
    plan_project_id: str
    title: str
    evidence_type: str
    publisher: str | None = None
    published_date: str | None = None
    geography: str | None = None
    plan_period: str | None = None
    status: str = Field(default="draft")
    source_url: str | None = None
    file_hash: str | None = None
    storage_path: str | None = None
    methodology_summary: str | None = None
    quality_flags: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)


class EvidenceGapCreate(BaseModel):
    plan_project_id: str
    gap_type: str
    triggered_by: str | None = None
    owner: str | None = None
    due_date: str | None = None
    risk_level: str | None = None
    resolution_evidence_item_id: str | None = None
    status: str = Field(default="open")


class TraceLinkCreate(BaseModel):
    from_type: str
    from_id: str
    to_type: str
    to_id: str
    link_type: str
    confidence: str | None = None
    notes: str | None = None
    created_by: str = Field(default="system")


def create_evidence_item(body: EvidenceItemCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO evidence_items (
          id, plan_project_id, title, evidence_type, publisher, published_date, geography, plan_period,
          status, source_url, file_hash, storage_path, methodology_summary, quality_flags_jsonb,
          dependencies_jsonb, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        RETURNING id, plan_project_id, title, evidence_type, publisher, published_date, geography, plan_period,
                  status, source_url, file_hash, storage_path, methodology_summary, quality_flags_jsonb,
                  dependencies_jsonb, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            body.title,
            body.evidence_type,
            body.publisher,
            body.published_date,
            body.geography,
            body.plan_period,
            body.status,
            body.source_url,
            body.file_hash,
            body.storage_path,
            body.methodology_summary,
            json.dumps(body.quality_flags, ensure_ascii=False),
            json.dumps(body.dependencies, ensure_ascii=False),
            now,
            now,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_evidence_item(row)))


def list_evidence_items(plan_project_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, plan_project_id, title, evidence_type, publisher, published_date, geography, plan_period,
               status, source_url, file_hash, storage_path, methodology_summary, quality_flags_jsonb,
               dependencies_jsonb, created_at, updated_at
        FROM evidence_items
        WHERE plan_project_id = %s::uuid
        ORDER BY updated_at DESC
        """,
        (plan_project_id,),
    )
    items = [_row_to_evidence_item(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"evidence_items": items}))


def create_evidence_gap(body: EvidenceGapCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO evidence_gaps (
          id, plan_project_id, gap_type, triggered_by, owner, due_date, risk_level,
          resolution_evidence_item_id, status, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s::uuid, %s, %s, %s)
        RETURNING id, plan_project_id, gap_type, triggered_by, owner, due_date, risk_level,
                  resolution_evidence_item_id, status, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            body.gap_type,
            body.triggered_by,
            body.owner,
            body.due_date,
            body.risk_level,
            body.resolution_evidence_item_id,
            body.status,
            now,
            now,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_evidence_gap(row)))


def list_evidence_gaps(plan_project_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, plan_project_id, gap_type, triggered_by, owner, due_date, risk_level,
               resolution_evidence_item_id, status, created_at, updated_at
        FROM evidence_gaps
        WHERE plan_project_id = %s::uuid
        ORDER BY updated_at DESC
        """,
        (plan_project_id,),
    )
    items = [_row_to_evidence_gap(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"evidence_gaps": items}))


def create_trace_link(body: TraceLinkCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO trace_links (
          id, from_type, from_id, to_type, to_id, link_type, confidence, notes, created_by, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, from_type, from_id, to_type, to_id, link_type, confidence, notes, created_by, created_at
        """,
        (
            str(uuid4()),
            body.from_type,
            body.from_id,
            body.to_type,
            body.to_id,
            body.link_type,
            body.confidence,
            body.notes,
            body.created_by,
            now,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_trace_link(row)))


def list_trace_links(from_type: str | None = None, from_id: str | None = None, to_type: str | None = None, to_id: str | None = None) -> JSONResponse:
    clauses = []
    params: list[Any] = []
    if from_type:
        clauses.append("from_type = %s")
        params.append(from_type)
    if from_id:
        clauses.append("from_id = %s")
        params.append(from_id)
    if to_type:
        clauses.append("to_type = %s")
        params.append(to_type)
    if to_id:
        clauses.append("to_id = %s")
        params.append(to_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = _db_fetch_all(
        f"""
        SELECT id, from_type, from_id, to_type, to_id, link_type, confidence, notes, created_by, created_at
        FROM trace_links
        {where}
        ORDER BY created_at DESC
        """,
        tuple(params),
    )
    items = [_row_to_trace_link(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"trace_links": items}))


def _row_to_evidence_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_item_id": str(row["id"]),
        "plan_project_id": str(row["plan_project_id"]),
        "title": row["title"],
        "evidence_type": row["evidence_type"],
        "publisher": row.get("publisher"),
        "published_date": row.get("published_date"),
        "geography": row.get("geography"),
        "plan_period": row.get("plan_period"),
        "status": row["status"],
        "source_url": row.get("source_url"),
        "file_hash": row.get("file_hash"),
        "storage_path": row.get("storage_path"),
        "methodology_summary": row.get("methodology_summary"),
        "quality_flags": row.get("quality_flags_jsonb") or {},
        "dependencies": row.get("dependencies_jsonb") or [],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_evidence_gap(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_gap_id": str(row["id"]),
        "plan_project_id": str(row["plan_project_id"]),
        "gap_type": row["gap_type"],
        "triggered_by": row.get("triggered_by"),
        "owner": row.get("owner"),
        "due_date": row.get("due_date"),
        "risk_level": row.get("risk_level"),
        "resolution_evidence_item_id": (
            str(row["resolution_evidence_item_id"]) if row.get("resolution_evidence_item_id") else None
        ),
        "status": row.get("status"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_trace_link(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "trace_link_id": str(row["id"]),
        "from_type": row["from_type"],
        "from_id": row["from_id"],
        "to_type": row["to_type"],
        "to_id": row["to_id"],
        "link_type": row["link_type"],
        "confidence": row.get("confidence"),
        "notes": row.get("notes"),
        "created_by": row.get("created_by"),
        "created_at": row["created_at"],
    }
