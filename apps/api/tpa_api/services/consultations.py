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


class ConsultationCreate(BaseModel):
    plan_project_id: str
    consultation_type: str
    title: str
    status: str = Field(default="draft")
    open_at: str | None = None
    close_at: str | None = None
    channels: list[str] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)


class ConsultationPatch(BaseModel):
    title: str | None = None
    status: str | None = None
    open_at: str | None = None
    close_at: str | None = None
    channels: list[str] | None = None
    documents: list[dict[str, Any]] | None = None


class InviteeCreate(BaseModel):
    consultation_id: str
    category: str
    name: str
    contact: dict[str, Any] = Field(default_factory=dict)
    invited_at: str | None = None
    method: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepresentationCreate(BaseModel):
    consultation_id: str
    submitter: dict[str, Any] = Field(default_factory=dict)
    content_text: str | None = None
    tags: list[str] = Field(default_factory=list)
    site_refs: list[str] = Field(default_factory=list)
    policy_refs: list[str] = Field(default_factory=list)
    files: list[dict[str, Any]] = Field(default_factory=list)
    submitted_at: str | None = None
    public_redacted_text: str | None = None
    status: str = Field(default="received")


class ConsultationSummaryCreate(BaseModel):
    consultation_id: str
    summary: dict[str, Any]
    status: str = Field(default="draft")


class IssueClusterCreate(BaseModel):
    consultation_id: str
    title: str
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    representation_ids: list[str] = Field(default_factory=list)


def create_consultation(body: ConsultationCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO consultations (
          id, plan_project_id, consultation_type, title, status, open_at, close_at,
          channels_jsonb, documents_jsonb, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        RETURNING id, plan_project_id, consultation_type, title, status, open_at, close_at,
                  channels_jsonb, documents_jsonb, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            body.consultation_type,
            body.title,
            body.status,
            body.open_at,
            body.close_at,
            json.dumps(body.channels, ensure_ascii=False),
            json.dumps(body.documents, ensure_ascii=False),
            now,
            now,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_consultation(row)))


def patch_consultation(consultation_id: str, body: ConsultationPatch) -> JSONResponse:
    row = _db_fetch_one("SELECT id FROM consultations WHERE id = %s::uuid", (consultation_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Consultation not found")
    updates = []
    params: list[Any] = []
    if body.title is not None:
        updates.append("title = %s")
        params.append(body.title)
    if body.status is not None:
        updates.append("status = %s")
        params.append(body.status)
    if body.open_at is not None:
        updates.append("open_at = %s")
        params.append(body.open_at)
    if body.close_at is not None:
        updates.append("close_at = %s")
        params.append(body.close_at)
    if body.channels is not None:
        updates.append("channels_jsonb = %s::jsonb")
        params.append(json.dumps(body.channels, ensure_ascii=False))
    if body.documents is not None:
        updates.append("documents_jsonb = %s::jsonb")
        params.append(json.dumps(body.documents, ensure_ascii=False))
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    now = _utc_now()
    params.append(now)
    params.append(consultation_id)
    _db_execute(
        f"UPDATE consultations SET {', '.join(updates)}, updated_at = %s WHERE id = %s::uuid",
        tuple(params),
    )
    return get_consultation(consultation_id)


def get_consultation(consultation_id: str) -> JSONResponse:
    row = _db_fetch_one(
        """
        SELECT id, plan_project_id, consultation_type, title, status, open_at, close_at,
               channels_jsonb, documents_jsonb, created_at, updated_at
        FROM consultations
        WHERE id = %s::uuid
        """,
        (consultation_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Consultation not found")
    return JSONResponse(content=jsonable_encoder(_row_to_consultation(row)))


def list_consultations(plan_project_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, plan_project_id, consultation_type, title, status, open_at, close_at,
               channels_jsonb, documents_jsonb, created_at, updated_at
        FROM consultations
        WHERE plan_project_id = %s::uuid
        ORDER BY updated_at DESC
        """,
        (plan_project_id,),
    )
    items = [_row_to_consultation(row) for row in rows]
    return JSONResponse(content=jsonable_encoder({"consultations": items}))


def create_invitee(body: InviteeCreate) -> JSONResponse:
    row = _db_execute_returning(
        """
        INSERT INTO invitees (
          id, consultation_id, category, name, contact_jsonb, invited_at, method, metadata_jsonb
        )
        VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
        RETURNING id, consultation_id, category, name, contact_jsonb, invited_at, method, metadata_jsonb
        """,
        (
            str(uuid4()),
            body.consultation_id,
            body.category,
            body.name,
            json.dumps(body.contact, ensure_ascii=False),
            body.invited_at,
            body.method,
            json.dumps(body.metadata, ensure_ascii=False),
        ),
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "invitee_id": str(row["id"]),
                "consultation_id": str(row["consultation_id"]),
                "category": row["category"],
                "name": row["name"],
                "contact": row.get("contact_jsonb") or {},
                "invited_at": row.get("invited_at"),
                "method": row.get("method"),
                "metadata": row.get("metadata_jsonb") or {},
            }
        )
    )


def list_invitees(consultation_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, consultation_id, category, name, contact_jsonb, invited_at, method, metadata_jsonb
        FROM invitees
        WHERE consultation_id = %s::uuid
        ORDER BY name
        """,
        (consultation_id,),
    )
    items = [
        {
            "invitee_id": str(r["id"]),
            "consultation_id": str(r["consultation_id"]),
            "category": r["category"],
            "name": r["name"],
            "contact": r.get("contact_jsonb") or {},
            "invited_at": r.get("invited_at"),
            "method": r.get("method"),
            "metadata": r.get("metadata_jsonb") or {},
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"invitees": items}))


def create_representation(body: RepresentationCreate) -> JSONResponse:
    submitted_at = body.submitted_at or _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO representations (
          id, consultation_id, submitter_jsonb, content_text, tags_jsonb, site_refs_jsonb,
          policy_refs_jsonb, files_jsonb, submitted_at, public_redacted_text, status
        )
        VALUES (%s, %s::uuid, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s)
        RETURNING id, consultation_id, submitter_jsonb, content_text, tags_jsonb, site_refs_jsonb,
                  policy_refs_jsonb, files_jsonb, submitted_at, public_redacted_text, status
        """,
        (
            str(uuid4()),
            body.consultation_id,
            json.dumps(body.submitter, ensure_ascii=False),
            body.content_text,
            json.dumps(body.tags, ensure_ascii=False),
            json.dumps(body.site_refs, ensure_ascii=False),
            json.dumps(body.policy_refs, ensure_ascii=False),
            json.dumps(body.files, ensure_ascii=False),
            submitted_at,
            body.public_redacted_text,
            body.status,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_representation(row)))


def list_representations(consultation_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, consultation_id, submitter_jsonb, content_text, tags_jsonb, site_refs_jsonb,
               policy_refs_jsonb, files_jsonb, submitted_at, public_redacted_text, status
        FROM representations
        WHERE consultation_id = %s::uuid
        ORDER BY submitted_at DESC NULLS LAST
        """,
        (consultation_id,),
    )
    items = [_row_to_representation(row) for row in rows]
    return JSONResponse(content=jsonable_encoder({"representations": items}))


def create_consultation_summary(body: ConsultationSummaryCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO consultation_summaries (
          id, consultation_id, summary_jsonb, status, published_at, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s::jsonb, %s, %s, %s, %s)
        RETURNING id, consultation_id, summary_jsonb, status, published_at, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.consultation_id,
            json.dumps(body.summary, ensure_ascii=False),
            body.status,
            now if body.status == "published" else None,
            now,
            now,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_summary(row)))


def create_issue_cluster(body: IssueClusterCreate) -> JSONResponse:
    row = _db_execute_returning(
        """
        INSERT INTO issue_clusters (
          id, consultation_id, title, summary, tags_jsonb, representation_ids_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s::jsonb, %s)
        RETURNING id, consultation_id, title, summary, tags_jsonb, representation_ids_jsonb, created_at
        """,
        (
            str(uuid4()),
            body.consultation_id,
            body.title,
            body.summary,
            json.dumps(body.tags, ensure_ascii=False),
            json.dumps(body.representation_ids, ensure_ascii=False),
            _utc_now(),
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_issue_cluster(row)))


def list_issue_clusters(consultation_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, consultation_id, title, summary, tags_jsonb, representation_ids_jsonb, created_at
        FROM issue_clusters
        WHERE consultation_id = %s::uuid
        ORDER BY created_at DESC
        """,
        (consultation_id,),
    )
    items = [_row_to_issue_cluster(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"issue_clusters": items}))


def publish_consultation_summary(summary_id: str) -> JSONResponse:
    now = _utc_now()
    _db_execute(
        "UPDATE consultation_summaries SET status = 'published', published_at = %s, updated_at = %s WHERE id = %s::uuid",
        (now, now, summary_id),
    )
    row = _db_fetch_one(
        """
        SELECT id, consultation_id, summary_jsonb, status, published_at, created_at, updated_at
        FROM consultation_summaries
        WHERE id = %s::uuid
        """,
        (summary_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Consultation summary not found")
    return JSONResponse(content=jsonable_encoder(_row_to_summary(row)))


def list_consultation_summaries(consultation_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, consultation_id, summary_jsonb, status, published_at, created_at, updated_at
        FROM consultation_summaries
        WHERE consultation_id = %s::uuid
        ORDER BY created_at DESC
        """,
        (consultation_id,),
    )
    items = [_row_to_summary(row) for row in rows]
    return JSONResponse(content=jsonable_encoder({"summaries": items}))


def _row_to_consultation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "consultation_id": str(row["id"]),
        "plan_project_id": str(row["plan_project_id"]),
        "consultation_type": row["consultation_type"],
        "title": row["title"],
        "status": row["status"],
        "open_at": row.get("open_at"),
        "close_at": row.get("close_at"),
        "channels": row.get("channels_jsonb") or [],
        "documents": row.get("documents_jsonb") or [],
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _row_to_representation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "representation_id": str(row["id"]),
        "consultation_id": str(row["consultation_id"]),
        "submitter": row.get("submitter_jsonb") or {},
        "content_text": row.get("content_text"),
        "tags": row.get("tags_jsonb") or [],
        "site_refs": row.get("site_refs_jsonb") or [],
        "policy_refs": row.get("policy_refs_jsonb") or [],
        "files": row.get("files_jsonb") or [],
        "submitted_at": row.get("submitted_at"),
        "public_redacted_text": row.get("public_redacted_text"),
        "status": row.get("status"),
    }


def _row_to_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary_id": str(row["id"]),
        "consultation_id": str(row["consultation_id"]),
        "summary": row.get("summary_jsonb") or {},
        "status": row.get("status"),
        "published_at": row.get("published_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _row_to_issue_cluster(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_cluster_id": str(row["id"]),
        "consultation_id": str(row["consultation_id"]),
        "title": row["title"],
        "summary": row.get("summary"),
        "tags": row.get("tags_jsonb") or [],
        "representation_ids": row.get("representation_ids_jsonb") or [],
        "created_at": row["created_at"],
    }
