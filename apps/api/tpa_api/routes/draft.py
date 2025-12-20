from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services import draft as draft_service


router = APIRouter(tags=["drafts"])


@router.post("/draft")
async def draft(request: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content=await draft_service.create_draft(request))
