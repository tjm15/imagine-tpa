from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.scenario_inspector import ScenarioInspectorRequest
from ..services.scenario_inspector import run_scenario_inspector as service_run_scenario_inspector


router = APIRouter(tags=["scenario-inspector"])


@router.post("/scenario-inspector")
def run_scenario_inspector(body: ScenarioInspectorRequest) -> JSONResponse:
    return service_run_scenario_inspector(body)
