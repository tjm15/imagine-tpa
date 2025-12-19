from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..api_utils import validate_uuid_or_400
from ..tool_requests import execute_tool_request_sync, get_tool_request, list_tool_requests_for_run


router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}/tool-requests")
def list_tool_requests(run_id: str, status: str | None = None, limit: int = 100) -> JSONResponse:
    run_id = validate_uuid_or_400(run_id, field_name="run_id")
    try:
        items = list_tool_requests_for_run(run_id=run_id, status=status, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=(
                f"Failed to query tool_requests: {exc}. "
                "If you recently pulled schema changes, reset the Postgres volume so init SQL runs (`./scripts/db_reset_oss.sh`)."
            ),
        ) from exc
    return JSONResponse(content=jsonable_encoder({"tool_requests": items}))


@router.get("/tool-requests/{tool_request_id}")
def get_tool_request_endpoint(tool_request_id: str) -> JSONResponse:
    tool_request = get_tool_request(tool_request_id=tool_request_id)
    if not tool_request:
        raise HTTPException(status_code=404, detail="ToolRequest not found")
    return JSONResponse(content=jsonable_encoder({"tool_request": tool_request}))


@router.post("/tool-requests/{tool_request_id}/run")
def run_tool_request(tool_request_id: str) -> JSONResponse:
    updated = execute_tool_request_sync(tool_request_id=tool_request_id)
    return JSONResponse(content=jsonable_encoder({"tool_request": updated}))

