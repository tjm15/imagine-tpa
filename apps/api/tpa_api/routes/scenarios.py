from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services import scenarios as scenarios_service
from ..services.scenarios import ScenarioCreate, ScenarioSetCreate, ScenarioTabRunRequest, ScenarioTabSelection


router = APIRouter(tags=["scenarios"])


@router.get("/scenarios")
def list_scenarios(
    plan_project_id: str | None = None,
    culp_stage_id: str | None = None,
    limit: int = 100,
) -> JSONResponse:
    return scenarios_service.list_scenarios(plan_project_id=plan_project_id, culp_stage_id=culp_stage_id, limit=limit)


@router.get("/scenario-sets")
def list_scenario_sets(
    plan_project_id: str | None = None,
    culp_stage_id: str | None = None,
    limit: int = 25,
) -> JSONResponse:
    return scenarios_service.list_scenario_sets(plan_project_id=plan_project_id, culp_stage_id=culp_stage_id, limit=limit)


@router.post("/scenarios")
def create_scenario(body: ScenarioCreate) -> JSONResponse:
    return scenarios_service.create_scenario(body)


@router.post("/scenario-sets")
def create_scenario_set(body: ScenarioSetCreate) -> JSONResponse:
    return scenarios_service.create_scenario_set(body)


@router.get("/scenario-sets/{scenario_set_id}")
def get_scenario_set(scenario_set_id: str) -> JSONResponse:
    return scenarios_service.get_scenario_set(scenario_set_id)


@router.post("/scenario-sets/{scenario_set_id}/select-tab")
def select_scenario_tab(scenario_set_id: str, body: ScenarioTabSelection) -> JSONResponse:
    return scenarios_service.select_scenario_tab(scenario_set_id, body)


@router.post("/scenario-framing-tabs/{tab_id}/run")
def run_scenario_framing_tab(tab_id: str, body: ScenarioTabRunRequest | None = None) -> JSONResponse:
    return scenarios_service.run_scenario_framing_tab(tab_id, body)


@router.get("/scenario-framing-tabs/{tab_id}/sheet")
def get_scenario_tab_sheet(tab_id: str) -> JSONResponse:
    return scenarios_service.get_scenario_tab_sheet(tab_id)
