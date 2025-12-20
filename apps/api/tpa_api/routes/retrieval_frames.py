from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.retrieval_frames import get_retrieval_frame as service_get_retrieval_frame
from ..services.retrieval_frames import list_retrieval_frames as service_list_retrieval_frames


router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}/retrieval-frames")
def list_retrieval_frames(
    run_id: str,
    move_type: str | None = None,
    current_only: bool = False,
    limit: int = 50,
) -> JSONResponse:
    return service_list_retrieval_frames(
        run_id=run_id,
        move_type=move_type,
        current_only=current_only,
        limit=limit,
    )


@router.get("/retrieval-frames/{retrieval_frame_id}")
def get_retrieval_frame(retrieval_frame_id: str) -> JSONResponse:
    return service_get_retrieval_frame(retrieval_frame_id)
