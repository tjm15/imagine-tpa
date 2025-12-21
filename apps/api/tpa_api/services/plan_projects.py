from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..audit import _audit_event
from ..spec_io import _read_yaml, _spec_root
from .culp_artefacts import ensure_culp_artefacts
from ..db import _db_execute_returning, _db_fetch_all
from ..time_utils import _utc_now


class PlanProjectCreate(BaseModel):
    authority_id: str
    process_model_id: str = Field(default="culp_30_month_v1")
    title: str
    status: str = Field(default="draft")
    current_stage_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _default_culp_stage(process_model_id: str) -> str | None:
    root = _spec_root()
    model = _read_yaml(root / "culp" / "PROCESS_MODEL.yaml")
    if not isinstance(model, dict) or model.get("process_id") != process_model_id:
        return None
    stages = model.get("stages")
    if not isinstance(stages, list) or not stages:
        return None
    first = stages[0]
    if isinstance(first, dict):
        return first.get("id")
    return None


def create_plan_project(body: PlanProjectCreate) -> JSONResponse:
    now = _utc_now()
    current_stage_id = body.current_stage_id or _default_culp_stage(body.process_model_id)
    row = _db_execute_returning(
        """
        INSERT INTO plan_projects (
          id, authority_id, process_model_id, title, status, current_stage_id,
          metadata_jsonb, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
        RETURNING id, authority_id, process_model_id, title, status, current_stage_id, metadata_jsonb, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.authority_id,
            body.process_model_id,
            body.title,
            body.status,
            current_stage_id,
            json.dumps(body.metadata, ensure_ascii=False),
            now,
            now,
        ),
    )
    ensure_culp_artefacts(str(row["id"]), body.process_model_id)
    _audit_event(
        event_type="plan_project_created",
        plan_project_id=str(row["id"]),
        payload={"authority_id": body.authority_id, "process_model_id": body.process_model_id},
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "plan_project_id": str(row["id"]),
                "authority_id": row["authority_id"],
                "process_model_id": row["process_model_id"],
                "title": row["title"],
                "status": row["status"],
                "current_stage_id": row["current_stage_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "metadata": row["metadata_jsonb"] or {},
            }
        )
    )


def list_plan_projects(authority_id: str | None = None) -> JSONResponse:
    if authority_id:
        rows = _db_fetch_all(
            """
            SELECT id, authority_id, process_model_id, title, status, current_stage_id, metadata_jsonb, created_at, updated_at
            FROM plan_projects
            WHERE authority_id = %s
            ORDER BY updated_at DESC
            """,
            (authority_id,),
        )
    else:
        rows = _db_fetch_all(
            """
            SELECT id, authority_id, process_model_id, title, status, current_stage_id, metadata_jsonb, created_at, updated_at
            FROM plan_projects
            ORDER BY updated_at DESC
            """
        )
    items = [
        {
            "plan_project_id": str(r["id"]),
            "authority_id": r["authority_id"],
            "process_model_id": r["process_model_id"],
            "title": r["title"],
            "status": r["status"],
            "current_stage_id": r["current_stage_id"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "metadata": r["metadata_jsonb"] or {},
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"plan_projects": items}))
