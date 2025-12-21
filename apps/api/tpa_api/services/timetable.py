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


class TimetableCreate(BaseModel):
    plan_project_id: str
    public_title: str
    plain_summary: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class TimetablePatch(BaseModel):
    public_title: str | None = None
    plain_summary: str | None = None
    data: dict[str, Any] | None = None
    status: str | None = None


class MilestoneCreate(BaseModel):
    timetable_id: str
    milestone_key: str
    title: str
    due_date: str | None = None
    status: str = Field(default="planned")
    metadata: dict[str, Any] = Field(default_factory=dict)


class MilestonePatch(BaseModel):
    title: str | None = None
    due_date: str | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None


class TimetableReviewCreate(BaseModel):
    timetable_id: str
    review_status: str
    reviewer: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_timetable(body: TimetableCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO timetables (
          id, plan_project_id, status, public_title, plain_summary, data_jsonb, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s, %s::jsonb, %s, %s)
        RETURNING id, plan_project_id, status, public_title, plain_summary, data_jsonb, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            "draft",
            body.public_title,
            body.plain_summary,
            json.dumps(body.data, ensure_ascii=False),
            now,
            now,
        ),
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "timetable_id": str(row["id"]),
                "plan_project_id": str(row["plan_project_id"]),
                "status": row["status"],
                "public_title": row["public_title"],
                "plain_summary": row["plain_summary"],
                "data": row.get("data_jsonb") or {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    )


def patch_timetable(timetable_id: str, body: TimetablePatch) -> JSONResponse:
    row = _db_fetch_one("SELECT id FROM timetables WHERE id = %s::uuid", (timetable_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Timetable not found")
    updates = []
    params: list[Any] = []
    if body.public_title is not None:
        updates.append("public_title = %s")
        params.append(body.public_title)
    if body.plain_summary is not None:
        updates.append("plain_summary = %s")
        params.append(body.plain_summary)
    if body.data is not None:
        updates.append("data_jsonb = %s::jsonb")
        params.append(json.dumps(body.data, ensure_ascii=False))
    if body.status is not None:
        updates.append("status = %s")
        params.append(body.status)
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    now = _utc_now()
    params.append(now)
    params.append(timetable_id)
    _db_execute(f"UPDATE timetables SET {', '.join(updates)}, updated_at = %s WHERE id = %s::uuid", tuple(params))
    return get_timetable(timetable_id)


def publish_timetable(timetable_id: str) -> JSONResponse:
    now = _utc_now()
    _db_execute(
        "UPDATE timetables SET status = 'published', published_at = %s, updated_at = %s WHERE id = %s::uuid",
        (now, now, timetable_id),
    )
    return get_timetable(timetable_id)


def get_timetable(timetable_id: str) -> JSONResponse:
    row = _db_fetch_one(
        """
        SELECT id, plan_project_id, status, public_title, plain_summary, data_jsonb,
               published_at, created_at, updated_at
        FROM timetables
        WHERE id = %s::uuid
        """,
        (timetable_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Timetable not found")
    return JSONResponse(
        content=jsonable_encoder(
            {
                "timetable_id": str(row["id"]),
                "plan_project_id": str(row["plan_project_id"]),
                "status": row["status"],
                "public_title": row["public_title"],
                "plain_summary": row["plain_summary"],
                "data": row.get("data_jsonb") or {},
                "published_at": row.get("published_at"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    )


def list_timetables(plan_project_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, plan_project_id, status, public_title, plain_summary, data_jsonb,
               published_at, created_at, updated_at
        FROM timetables
        WHERE plan_project_id = %s::uuid
        ORDER BY updated_at DESC
        """,
        (plan_project_id,),
    )
    items = [
        {
            "timetable_id": str(r["id"]),
            "plan_project_id": str(r["plan_project_id"]),
            "status": r["status"],
            "public_title": r["public_title"],
            "plain_summary": r["plain_summary"],
            "data": r.get("data_jsonb") or {},
            "published_at": r.get("published_at"),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"timetables": items}))


def create_milestone(body: MilestoneCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO milestones (
          id, timetable_id, milestone_key, title, due_date, status, metadata_jsonb, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s)
        RETURNING id, timetable_id, milestone_key, title, due_date, status, metadata_jsonb, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.timetable_id,
            body.milestone_key,
            body.title,
            body.due_date,
            body.status,
            json.dumps(body.metadata, ensure_ascii=False),
            now,
            now,
        ),
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "milestone_id": str(row["id"]),
                "timetable_id": str(row["timetable_id"]),
                "milestone_key": row["milestone_key"],
                "title": row["title"],
                "due_date": row["due_date"],
                "status": row["status"],
                "metadata": row.get("metadata_jsonb") or {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    )


def patch_milestone(milestone_id: str, body: MilestonePatch) -> JSONResponse:
    row = _db_fetch_one("SELECT id FROM milestones WHERE id = %s::uuid", (milestone_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Milestone not found")
    updates = []
    params: list[Any] = []
    if body.title is not None:
        updates.append("title = %s")
        params.append(body.title)
    if body.due_date is not None:
        updates.append("due_date = %s")
        params.append(body.due_date)
    if body.status is not None:
        updates.append("status = %s")
        params.append(body.status)
    if body.metadata is not None:
        updates.append("metadata_jsonb = %s::jsonb")
        params.append(json.dumps(body.metadata, ensure_ascii=False))
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    now = _utc_now()
    params.append(now)
    params.append(milestone_id)
    _db_execute(f"UPDATE milestones SET {', '.join(updates)}, updated_at = %s WHERE id = %s::uuid", tuple(params))
    row = _db_fetch_one(
        """
        SELECT id, timetable_id, milestone_key, title, due_date, status, metadata_jsonb, created_at, updated_at
        FROM milestones
        WHERE id = %s::uuid
        """,
        (milestone_id,),
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "milestone_id": str(row["id"]),
                "timetable_id": str(row["timetable_id"]),
                "milestone_key": row["milestone_key"],
                "title": row["title"],
                "due_date": row["due_date"],
                "status": row["status"],
                "metadata": row.get("metadata_jsonb") or {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    )


def list_milestones(timetable_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, timetable_id, milestone_key, title, due_date, status, metadata_jsonb, created_at, updated_at
        FROM milestones
        WHERE timetable_id = %s::uuid
        ORDER BY due_date NULLS LAST, created_at ASC
        """,
        (timetable_id,),
    )
    items = [
        {
            "milestone_id": str(r["id"]),
            "timetable_id": str(r["timetable_id"]),
            "milestone_key": r["milestone_key"],
            "title": r["title"],
            "due_date": r["due_date"],
            "status": r["status"],
            "metadata": r.get("metadata_jsonb") or {},
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"milestones": items}))


def create_timetable_review(body: TimetableReviewCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO timetable_reviews (
          id, timetable_id, review_status, reviewed_at, reviewer, notes, metadata_jsonb
        )
        VALUES (%s, %s::uuid, %s, %s, %s, %s, %s::jsonb)
        RETURNING id, timetable_id, review_status, reviewed_at, reviewer, notes, metadata_jsonb
        """,
        (
            str(uuid4()),
            body.timetable_id,
            body.review_status,
            now,
            body.reviewer,
            body.notes,
            json.dumps(body.metadata, ensure_ascii=False),
        ),
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "review_id": str(row["id"]),
                "timetable_id": str(row["timetable_id"]),
                "review_status": row["review_status"],
                "reviewed_at": row["reviewed_at"],
                "reviewer": row.get("reviewer"),
                "notes": row.get("notes"),
                "metadata": row.get("metadata_jsonb") or {},
            }
        )
    )


def list_timetable_reviews(timetable_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, timetable_id, review_status, reviewed_at, reviewer, notes, metadata_jsonb
        FROM timetable_reviews
        WHERE timetable_id = %s::uuid
        ORDER BY reviewed_at DESC
        """,
        (timetable_id,),
    )
    items = [
        {
            "review_id": str(r["id"]),
            "timetable_id": str(r["timetable_id"]),
            "review_status": r["review_status"],
            "reviewed_at": r["reviewed_at"],
            "reviewer": r.get("reviewer"),
            "notes": r.get("notes"),
            "metadata": r.get("metadata_jsonb") or {},
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"reviews": items}))
