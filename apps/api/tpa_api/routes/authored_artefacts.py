from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.authored_artefacts import (
    AuthoredArtefactCreate,
    AuthoredArtefactPatch,
    create_authored_artefact as service_create_authored_artefact,
    get_authored_artefact as service_get_authored_artefact,
    list_authored_artefacts as service_list_authored_artefacts,
    patch_authored_artefact as service_patch_authored_artefact,
)


router = APIRouter(tags=["authored-artefacts"])


@router.post("/authored-artefacts")
def create_authored_artefact(body: AuthoredArtefactCreate) -> JSONResponse:
    return service_create_authored_artefact(body)


@router.get("/authored-artefacts")
def list_authored_artefacts(
    plan_project_id: str | None = None,
    application_id: str | None = None,
    workspace: str | None = None,
    artefact_type: str | None = None,
    limit: int = 20,
) -> JSONResponse:
    return service_list_authored_artefacts(
        plan_project_id=plan_project_id,
        application_id=application_id,
        workspace=workspace,
        artefact_type=artefact_type,
        limit=limit,
    )


@router.get("/authored-artefacts/{authored_artefact_id}")
def get_authored_artefact(authored_artefact_id: str) -> JSONResponse:
    return service_get_authored_artefact(authored_artefact_id)


@router.patch("/authored-artefacts/{authored_artefact_id}")
def patch_authored_artefact(authored_artefact_id: str, body: AuthoredArtefactPatch) -> JSONResponse:
    return service_patch_authored_artefact(authored_artefact_id, body)
