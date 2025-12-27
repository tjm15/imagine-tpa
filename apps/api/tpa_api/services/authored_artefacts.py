from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..api_utils import validate_uuid_or_400
from ..audit import _audit_event
from ..db import _db_execute, _db_execute_returning, _db_fetch_all, _db_fetch_one
from ..time_utils import _utc_now


class AuthoredArtefactCreate(BaseModel):
    workspace: str
    artefact_type: str
    title: str
    plan_project_id: str | None = None
    application_id: str | None = None
    culp_stage_id: str | None = None
    status: str = Field(default="draft")
    content_format: str = Field(default="tiptap_json")
    content_jsonb: dict[str, Any] | None = None
    created_by: str = Field(default="planner")
    supersedes_artefact_id: str | None = None


class AuthoredArtefactPatch(BaseModel):
    title: str | None = None
    status: str | None = None
    content_format: str | None = None
    content_jsonb: dict[str, Any] | None = None
    exported_artifact_path: str | None = None
    supersedes_artefact_id: str | None = None


def _default_content(title: str) -> dict[str, Any]:
    safe_title = title.strip() or "Draft"
    return {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": safe_title}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Start drafting here."}],
            },
        ],
    }


def create_authored_artefact(body: AuthoredArtefactCreate) -> JSONResponse:
    workspace = (body.workspace or "").strip()
    artefact_type = (body.artefact_type or "").strip()
    title = (body.title or "").strip()
    if not workspace:
        raise HTTPException(status_code=400, detail="workspace must not be empty")
    if not artefact_type:
        raise HTTPException(status_code=400, detail="artefact_type must not be empty")
    if not title:
        raise HTTPException(status_code=400, detail="title must not be empty")

    plan_project_id = validate_uuid_or_400(body.plan_project_id, field_name="plan_project_id") if body.plan_project_id else None
    application_id = validate_uuid_or_400(body.application_id, field_name="application_id") if body.application_id else None
    culp_stage_id = validate_uuid_or_400(body.culp_stage_id, field_name="culp_stage_id") if body.culp_stage_id else None
    supersedes = (
        validate_uuid_or_400(body.supersedes_artefact_id, field_name="supersedes_artefact_id")
        if body.supersedes_artefact_id
        else None
    )

    if not plan_project_id and not application_id:
        raise HTTPException(status_code=400, detail="Either plan_project_id or application_id is required")

    content_jsonb = body.content_jsonb if isinstance(body.content_jsonb, dict) else _default_content(title)
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO authored_artefacts (
          id, workspace, plan_project_id, application_id, culp_stage_id, artefact_type,
          title, status, content_format, content_jsonb, exported_artifact_path,
          supersedes_artefact_id, created_by, created_at, updated_at
        )
        VALUES (%s, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb, NULL, %s::uuid, %s, %s, %s)
        RETURNING id, workspace, plan_project_id, application_id, culp_stage_id, artefact_type,
                  title, status, content_format, content_jsonb, exported_artifact_path,
                  supersedes_artefact_id, created_by, created_at, updated_at
        """,
        (
            str(uuid4()),
            workspace,
            plan_project_id,
            application_id,
            culp_stage_id,
            artefact_type,
            title,
            body.status,
            body.content_format,
            json.dumps(content_jsonb, ensure_ascii=False),
            supersedes,
            body.created_by,
            now,
            now,
        ),
    )
    _audit_event(
        event_type="authored_artefact_created",
        plan_project_id=plan_project_id,
        payload={
            "authored_artefact_id": str(row["id"]),
            "workspace": workspace,
            "artefact_type": artefact_type,
            "application_id": application_id,
        },
    )
    return JSONResponse(content=jsonable_encoder(_row_to_authored_artefact(row)))


def list_authored_artefacts(
    *,
    plan_project_id: str | None = None,
    application_id: str | None = None,
    workspace: str | None = None,
    artefact_type: str | None = None,
    limit: int = 20,
) -> JSONResponse:
    clauses: list[str] = []
    params: list[Any] = []
    if plan_project_id:
        clauses.append("plan_project_id = %s::uuid")
        params.append(validate_uuid_or_400(plan_project_id, field_name="plan_project_id"))
    if application_id:
        clauses.append("application_id = %s::uuid")
        params.append(validate_uuid_or_400(application_id, field_name="application_id"))
    if workspace:
        clauses.append("workspace = %s")
        params.append(workspace)
    if artefact_type:
        clauses.append("artefact_type = %s")
        params.append(artefact_type)

    limit = max(1, min(int(limit or 20), 100))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = _db_fetch_all(
        f"""
        SELECT id, workspace, plan_project_id, application_id, culp_stage_id, artefact_type,
               title, status, content_format, content_jsonb, exported_artifact_path,
               supersedes_artefact_id, created_by, created_at, updated_at
        FROM authored_artefacts
        {where}
        ORDER BY updated_at DESC
        LIMIT {limit}
        """,
        tuple(params),
    )
    items = [_row_to_authored_artefact(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"authored_artefacts": items}))


def get_authored_artefact(authored_artefact_id: str) -> JSONResponse:
    authored_artefact_id = validate_uuid_or_400(authored_artefact_id, field_name="authored_artefact_id")
    row = _db_fetch_one(
        """
        SELECT id, workspace, plan_project_id, application_id, culp_stage_id, artefact_type,
               title, status, content_format, content_jsonb, exported_artifact_path,
               supersedes_artefact_id, created_by, created_at, updated_at
        FROM authored_artefacts
        WHERE id = %s::uuid
        """,
        (authored_artefact_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Authored artefact not found")
    return JSONResponse(content=jsonable_encoder(_row_to_authored_artefact(row)))


def patch_authored_artefact(authored_artefact_id: str, body: AuthoredArtefactPatch) -> JSONResponse:
    authored_artefact_id = validate_uuid_or_400(authored_artefact_id, field_name="authored_artefact_id")
    existing = _db_fetch_one(
        "SELECT id, plan_project_id, application_id FROM authored_artefacts WHERE id = %s::uuid",
        (authored_artefact_id,),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Authored artefact not found")

    supersedes = (
        validate_uuid_or_400(body.supersedes_artefact_id, field_name="supersedes_artefact_id")
        if body.supersedes_artefact_id
        else None
    )
    now = _utc_now()
    row = _db_execute_returning(
        """
        UPDATE authored_artefacts
        SET
          title = COALESCE(%s, title),
          status = COALESCE(%s, status),
          content_format = COALESCE(%s, content_format),
          content_jsonb = COALESCE(%s::jsonb, content_jsonb),
          exported_artifact_path = COALESCE(%s, exported_artifact_path),
          supersedes_artefact_id = COALESCE(%s::uuid, supersedes_artefact_id),
          updated_at = %s
        WHERE id = %s::uuid
        RETURNING id, workspace, plan_project_id, application_id, culp_stage_id, artefact_type,
                  title, status, content_format, content_jsonb, exported_artifact_path,
                  supersedes_artefact_id, created_by, created_at, updated_at
        """,
        (
            body.title,
            body.status,
            body.content_format,
            json.dumps(body.content_jsonb, ensure_ascii=False) if body.content_jsonb is not None else None,
            body.exported_artifact_path,
            supersedes,
            now,
            authored_artefact_id,
        ),
    )
    _audit_event(
        event_type="authored_artefact_updated",
        plan_project_id=str(existing.get("plan_project_id")) if existing.get("plan_project_id") else None,
        payload={
            "authored_artefact_id": authored_artefact_id,
            "application_id": str(existing.get("application_id")) if existing.get("application_id") else None,
        },
    )
    return JSONResponse(content=jsonable_encoder(_row_to_authored_artefact(row)))


def _row_to_authored_artefact(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "authored_artefact_id": str(row["id"]),
        "workspace": row.get("workspace"),
        "plan_project_id": str(row["plan_project_id"]) if row.get("plan_project_id") else None,
        "application_id": str(row["application_id"]) if row.get("application_id") else None,
        "culp_stage_id": str(row["culp_stage_id"]) if row.get("culp_stage_id") else None,
        "artefact_type": row.get("artefact_type"),
        "title": row.get("title"),
        "status": row.get("status"),
        "content_format": row.get("content_format"),
        "content": row.get("content_jsonb") or {},
        "exported_artifact_path": row.get("exported_artifact_path"),
        "supersedes_artefact_id": (
            str(row.get("supersedes_artefact_id")) if row.get("supersedes_artefact_id") else None
        ),
        "created_by": row.get("created_by"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }
