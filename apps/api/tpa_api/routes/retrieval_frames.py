from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..api_utils import validate_uuid_or_400
from ..db import _db_fetch_all, _db_fetch_one


router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}/retrieval-frames")
def list_retrieval_frames(
    run_id: str,
    move_type: str | None = None,
    current_only: bool = False,
    limit: int = 50,
) -> JSONResponse:
    run_id = validate_uuid_or_400(run_id, field_name="run_id")
    limit = max(1, min(int(limit), 200))

    where: list[str] = ["run_id = %s::uuid"]
    params: list[Any] = [run_id]
    if move_type:
        where.append("move_type = %s")
        params.append(move_type)
    if current_only:
        where.append("is_current = true")

    where_sql = " AND ".join(where)
    try:
        rows = _db_fetch_all(
            f"""
            SELECT id, run_id, move_type, version, is_current, superseded_by_frame_id, tool_run_id, frame_jsonb, created_at
            FROM retrieval_frames
            WHERE {where_sql}
            ORDER BY created_at DESC, version DESC
            LIMIT %s
            """,
            tuple(params + [limit]),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=(
                f"Failed to query retrieval_frames: {exc}. "
                "If you recently pulled schema changes, reset the Postgres volume so init SQL runs (`./scripts/db_reset_oss.sh`)."
            ),
        ) from exc

    frames = []
    for r in rows:
        frames.append(
            {
                "retrieval_frame_id": str(r["id"]),
                "run_id": str(r["run_id"]),
                "move_type": r["move_type"],
                "version": r["version"],
                "is_current": r["is_current"],
                "superseded_by_retrieval_frame_id": str(r["superseded_by_frame_id"]) if r.get("superseded_by_frame_id") else None,
                "tool_run_id": str(r["tool_run_id"]) if r.get("tool_run_id") else None,
                "frame": r.get("frame_jsonb") or {},
                "created_at": r.get("created_at"),
            }
        )

    return JSONResponse(content=jsonable_encoder({"retrieval_frames": frames}))


@router.get("/retrieval-frames/{retrieval_frame_id}")
def get_retrieval_frame(retrieval_frame_id: str) -> JSONResponse:
    retrieval_frame_id = validate_uuid_or_400(retrieval_frame_id, field_name="retrieval_frame_id")
    row = _db_fetch_one(
        """
        SELECT id, run_id, move_type, version, is_current, superseded_by_frame_id, tool_run_id, frame_jsonb, created_at
        FROM retrieval_frames
        WHERE id = %s::uuid
        """,
        (retrieval_frame_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="RetrievalFrame not found")

    frame = {
        "retrieval_frame_id": str(row["id"]),
        "run_id": str(row["run_id"]),
        "move_type": row["move_type"],
        "version": row["version"],
        "is_current": row["is_current"],
        "superseded_by_retrieval_frame_id": str(row["superseded_by_frame_id"]) if row.get("superseded_by_frame_id") else None,
        "tool_run_id": str(row["tool_run_id"]) if row.get("tool_run_id") else None,
        "frame": row.get("frame_jsonb") or {},
        "created_at": row.get("created_at"),
    }
    return JSONResponse(content=jsonable_encoder({"retrieval_frame": frame}))

