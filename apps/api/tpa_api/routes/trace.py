from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.trace import trace_run as service_trace_run


router = APIRouter(tags=["trace"])


@router.get("/trace/runs/{run_id}")
def trace_run(run_id: str, mode: str = "summary") -> JSONResponse:
    return service_trace_run(run_id, mode=mode)
