from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.examination import AdoptionStatementCreate, ExaminationEventCreate
from ..services.examination import create_adoption_statement as service_create_adoption_statement
from ..services.examination import create_examination_event as service_create_examination_event
from ..services.examination import list_adoption_statements as service_list_adoption_statements
from ..services.examination import list_examination_events as service_list_examination_events


router = APIRouter(tags=["examination"])


@router.post("/examination/events")
def create_examination_event(body: ExaminationEventCreate) -> JSONResponse:
    return service_create_examination_event(body)


@router.get("/plan-projects/{plan_project_id}/examination/events")
def list_examination_events(plan_project_id: str) -> JSONResponse:
    return service_list_examination_events(plan_project_id)


@router.post("/adoption/statements")
def create_adoption_statement(body: AdoptionStatementCreate) -> JSONResponse:
    return service_create_adoption_statement(body)


@router.get("/plan-projects/{plan_project_id}/adoption/statements")
def list_adoption_statements(plan_project_id: str) -> JSONResponse:
    return service_list_adoption_statements(plan_project_id)
