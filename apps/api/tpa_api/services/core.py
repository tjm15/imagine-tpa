from __future__ import annotations

from fastapi import HTTPException

from ..db import db_ping


def healthz() -> dict[str, str]:
    return {"status": "ok"}


def readyz() -> dict[str, str]:
    if not db_ping():
        raise HTTPException(status_code=503, detail={"status": "not_ready", "db": "down"})
    return {"status": "ready", "db": "ok"}
