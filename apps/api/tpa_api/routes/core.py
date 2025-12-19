from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..db import db_ping


router = APIRouter(tags=["core"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    if not db_ping():
        raise HTTPException(status_code=503, detail={"status": "not_ready", "db": "down"})
    return {"status": "ready", "db": "ok"}
