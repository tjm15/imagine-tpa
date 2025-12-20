from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.tool_requests import get_tool_request_endpoint as service_get_tool_request
from ..services.tool_requests import list_tool_requests as service_list_tool_requests
from ..services.tool_requests import run_tool_request as service_run_tool_request


router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}/tool-requests")
def list_tool_requests(run_id: str, status: str | None = None, limit: int = 100) -> JSONResponse:
    return service_list_tool_requests(run_id=run_id, status=status, limit=limit)


@router.get("/tool-requests/{tool_request_id}")
def get_tool_request_endpoint(tool_request_id: str) -> JSONResponse:
    return service_get_tool_request(tool_request_id)


@router.post("/tool-requests/{tool_request_id}/run")
def run_tool_request(tool_request_id: str) -> JSONResponse:
    return service_run_tool_request(tool_request_id)
