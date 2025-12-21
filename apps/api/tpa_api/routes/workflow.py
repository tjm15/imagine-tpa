from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..services.workflow import advance_workflow as service_advance_workflow
from ..services.workflow import get_workflow_status as service_get_workflow_status
from ..services.workflow import init_plan_workflow as service_init_plan_workflow


router = APIRouter(tags=["workflow"])


class WorkflowInitRequest(BaseModel):
    rule_pack_version_id: str


class WorkflowAdvanceRequest(BaseModel):
    to_state_id: str
    actor_type: str | None = None


@router.post("/plan-projects/{plan_project_id}/workflow/init")
def init_workflow(plan_project_id: str, body: WorkflowInitRequest) -> JSONResponse:
    return service_init_plan_workflow(plan_project_id, body.rule_pack_version_id)


@router.get("/plan-projects/{plan_project_id}/workflow")
def get_workflow(plan_project_id: str) -> JSONResponse:
    return service_get_workflow_status(plan_project_id)


@router.post("/plan-projects/{plan_project_id}/workflow/advance")
def advance_workflow(plan_project_id: str, body: WorkflowAdvanceRequest) -> JSONResponse:
    return service_advance_workflow(
        plan_project_id, body.to_state_id, actor_type=body.actor_type or "system"
    )
