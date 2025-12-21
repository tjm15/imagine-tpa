from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.applications import ApplicationCreate, DecisionCreate
from ..services.applications import create_application as service_create_application
from ..services.applications import create_decision as service_create_decision
from ..services.applications import list_applications as service_list_applications
from ..services.applications import list_decisions as service_list_decisions


router = APIRouter(tags=["applications"])


@router.post("/applications")
def create_application(body: ApplicationCreate) -> JSONResponse:
    return service_create_application(body)


@router.get("/applications")
def list_applications(authority_id: str) -> JSONResponse:
    return service_list_applications(authority_id)


@router.post("/applications/{application_id}/decisions")
def create_decision(application_id: str, body: DecisionCreate) -> JSONResponse:
    payload = body.model_dump()
    payload["application_id"] = application_id
    return service_create_decision(DecisionCreate(**payload))


@router.get("/applications/{application_id}/decisions")
def list_decisions(application_id: str) -> JSONResponse:
    return service_list_decisions(application_id)
