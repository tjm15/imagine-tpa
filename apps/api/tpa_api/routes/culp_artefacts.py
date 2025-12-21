from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..services.culp_artefacts import list_culp_artefacts as service_list_culp_artefacts
from ..services.culp_artefacts import update_culp_artefact as service_update_culp_artefact


router = APIRouter(tags=["culp-artefacts"])


class CulpArtefactUpdate(BaseModel):
    status: str | None = None
    authored_artefact_id: str | None = None
    artifact_path: str | None = None
    evidence_refs: list[str] | None = None
    notes: str | None = None


@router.get("/plan-projects/{plan_project_id}/culp-artefacts")
def list_culp_artefacts(plan_project_id: str) -> JSONResponse:
    return service_list_culp_artefacts(plan_project_id)


@router.patch("/culp-artefacts/{culp_artefact_id}")
def patch_culp_artefact(culp_artefact_id: str, body: CulpArtefactUpdate) -> JSONResponse:
    return service_update_culp_artefact(culp_artefact_id, body.model_dump(exclude_unset=True))
