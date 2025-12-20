from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services import spec as spec_service


router = APIRouter(tags=["spec"])


@router.get("/spec/culp/process-model")
def culp_process_model() -> JSONResponse:
    return spec_service.culp_process_model()


@router.get("/spec/culp/artefact-registry")
def culp_artefact_registry() -> JSONResponse:
    return spec_service.culp_artefact_registry()


@router.get("/spec/authorities/selected")
def selected_authorities() -> JSONResponse:
    return spec_service.selected_authorities()


@router.get("/spec/framing/political-framings")
def political_framings() -> JSONResponse:
    return spec_service.political_framings()


@router.get("/spec/schemas")
def list_schemas() -> dict[str, list[str]]:
    return spec_service.list_schemas()


@router.get("/spec/schemas/{schema_name}")
def get_schema(schema_name: str) -> JSONResponse:
    return spec_service.get_schema(schema_name)
