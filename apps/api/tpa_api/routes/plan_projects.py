from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.plan_projects import PlanProjectCreate
from ..services.plan_projects import create_plan_project as service_create_plan_project
from ..services.plan_projects import list_plan_projects as service_list_plan_projects


router = APIRouter(tags=["plan-projects"])


@router.post("/plan-projects")
def create_plan_project(body: PlanProjectCreate) -> JSONResponse:
    return service_create_plan_project(body)


@router.get("/plan-projects")
def list_plan_projects(authority_id: str | None = None) -> JSONResponse:
    return service_list_plan_projects(authority_id=authority_id)
