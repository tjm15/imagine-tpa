from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import _db_execute_returning
from ..time_utils import _utc_now


class RunCreate(BaseModel):
    profile: str | None = None
    culp_stage_id: str | None = None
    anchors: dict[str, Any] = Field(default_factory=dict)


def create_run(body: RunCreate) -> JSONResponse:
    profile = body.profile or os.environ.get("TPA_PROFILE", "oss")
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO runs (id, profile, culp_stage_id, anchors_jsonb, created_at)
        VALUES (%s, %s, %s, %s::jsonb, %s)
        RETURNING id, profile, culp_stage_id, anchors_jsonb, created_at
        """,
        (
            str(uuid4()),
            profile,
            body.culp_stage_id,
            json.dumps(body.anchors, ensure_ascii=False),
            now,
        ),
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "run_id": str(row["id"]),
                "profile": row["profile"],
                "culp_stage_id": row.get("culp_stage_id"),
                "anchors": row.get("anchors_jsonb") or {},
                "created_at": row["created_at"],
            }
        )
    )
