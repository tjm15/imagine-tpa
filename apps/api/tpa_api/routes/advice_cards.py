from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.advice_cards import list_advice_cards as service_list_advice_cards

router = APIRouter(tags=["advice-cards"])


@router.get("/advice-cards")
def list_advice_cards(
    plan_project_id: str | None = None,
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    limit: int = 200,
) -> JSONResponse:
    return service_list_advice_cards(
        plan_project_id=plan_project_id,
        authority_id=authority_id,
        plan_cycle_id=plan_cycle_id,
        limit=limit,
    )
