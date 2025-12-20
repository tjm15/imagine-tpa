from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.plan_cycles import PlanCycleCreate, PlanCyclePatch
from ..services.plan_cycles import create_plan_cycle as service_create_plan_cycle
from ..services.plan_cycles import list_plan_cycles as service_list_plan_cycles
from ..services.plan_cycles import patch_plan_cycle as service_patch_plan_cycle


router = APIRouter(tags=["plan-cycles"])


@router.post("/plan-cycles")
def create_plan_cycle(body: PlanCycleCreate) -> JSONResponse:
    return service_create_plan_cycle(body)


@router.patch("/plan-cycles/{plan_cycle_id}")
def patch_plan_cycle(plan_cycle_id: str, body: PlanCyclePatch) -> JSONResponse:
    return service_patch_plan_cycle(plan_cycle_id, body)


@router.get("/plan-cycles")
def list_plan_cycles(authority_id: str | None = None, active_only: bool = True) -> JSONResponse:
    return service_list_plan_cycles(authority_id=authority_id, active_only=active_only)
