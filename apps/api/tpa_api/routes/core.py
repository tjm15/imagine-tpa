from __future__ import annotations

from fastapi import APIRouter

from ..services.core import healthz as service_healthz
from ..services.core import readyz as service_readyz


router = APIRouter(tags=["core"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return service_healthz()


@router.get("/readyz")
def readyz() -> dict[str, str]:
    return service_readyz()
