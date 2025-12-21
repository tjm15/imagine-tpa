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


class PublicationCreate(BaseModel):
    plan_project_id: str
    artefact_key: str
    title: str
    authored_artefact_id: str | None = None
    artifact_path: str | None = None
    status: str = Field(default="draft")
    publish_target: str = Field(default="public")
    is_immutable: bool = Field(default=False)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PublicationAssetCreate(BaseModel):
    publication_id: str
    asset_path: str
    content_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_publication(body: PublicationCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO publications (
          id, plan_project_id, artefact_key, authored_artefact_id, artifact_path, title,
          status, publish_target, is_immutable, published_at, metadata_jsonb, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s, %s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
        RETURNING id, plan_project_id, artefact_key, authored_artefact_id, artifact_path, title,
                  status, publish_target, is_immutable, published_at, metadata_jsonb, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            body.artefact_key,
            body.authored_artefact_id,
            body.artifact_path,
            body.title,
            body.status,
            body.publish_target,
            body.is_immutable,
            now if body.status == "published" else None,
            json.dumps(body.metadata, ensure_ascii=False),
            now,
            now,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_publication(row)))


def publish_publication(publication_id: str) -> JSONResponse:
    now = _utc_now()
    _db_execute(
        "UPDATE publications SET status = 'published', published_at = %s, updated_at = %s WHERE id = %s::uuid",
        (now, now, publication_id),
    )
    return get_publication(publication_id)


def get_publication(publication_id: str) -> JSONResponse:
    row = _db_fetch_one(
        """
        SELECT id, plan_project_id, artefact_key, authored_artefact_id, artifact_path, title,
               status, publish_target, is_immutable, published_at, metadata_jsonb, created_at, updated_at
        FROM publications
        WHERE id = %s::uuid
        """,
        (publication_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Publication not found")
    return JSONResponse(content=jsonable_encoder(_row_to_publication(row)))


def list_publications(plan_project_id: str, status: str | None = None) -> JSONResponse:
    params: list[Any] = [plan_project_id]
    clause = ""
    if status:
        clause = "AND status = %s"
        params.append(status)
    rows = _db_fetch_all(
        f"""
        SELECT id, plan_project_id, artefact_key, authored_artefact_id, artifact_path, title,
               status, publish_target, is_immutable, published_at, metadata_jsonb, created_at, updated_at
        FROM publications
        WHERE plan_project_id = %s::uuid {clause}
        ORDER BY updated_at DESC
        """,
        tuple(params),
    )
    items = [_row_to_publication(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"publications": items}))


def create_publication_asset(body: PublicationAssetCreate) -> JSONResponse:
    row = _db_execute_returning(
        """
        INSERT INTO publication_assets (
          id, publication_id, asset_path, content_type, metadata_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
        RETURNING id, publication_id, asset_path, content_type, metadata_jsonb, created_at
        """,
        (
            str(uuid4()),
            body.publication_id,
            body.asset_path,
            body.content_type,
            json.dumps(body.metadata, ensure_ascii=False),
            _utc_now(),
        ),
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "publication_asset_id": str(row["id"]),
                "publication_id": str(row["publication_id"]),
                "asset_path": row["asset_path"],
                "content_type": row["content_type"],
                "metadata": row.get("metadata_jsonb") or {},
                "created_at": row["created_at"],
            }
        )
    )


def list_publication_assets(publication_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, publication_id, asset_path, content_type, metadata_jsonb, created_at
        FROM publication_assets
        WHERE publication_id = %s::uuid
        ORDER BY created_at DESC
        """,
        (publication_id,),
    )
    items = [
        {
            "publication_asset_id": str(r["id"]),
            "publication_id": str(r["publication_id"]),
            "asset_path": r["asset_path"],
            "content_type": r["content_type"],
            "metadata": r.get("metadata_jsonb") or {},
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"publication_assets": items}))


def _row_to_publication(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "publication_id": str(row["id"]),
        "plan_project_id": str(row["plan_project_id"]),
        "artefact_key": row["artefact_key"],
        "authored_artefact_id": (
            str(row["authored_artefact_id"]) if row.get("authored_artefact_id") else None
        ),
        "artifact_path": row.get("artifact_path"),
        "title": row["title"],
        "status": row["status"],
        "publish_target": row["publish_target"],
        "is_immutable": bool(row.get("is_immutable")),
        "published_at": row.get("published_at"),
        "metadata": row.get("metadata_jsonb") or {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
