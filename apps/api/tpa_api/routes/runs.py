from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.runs import RunCreate
from ..services.runs import create_run as service_create_run


router = APIRouter(tags=["runs"])


@router.post("/runs")
def create_run(body: RunCreate) -> JSONResponse:
    return service_create_run(body)
