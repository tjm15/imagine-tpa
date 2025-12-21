from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.publications import PublicationAssetCreate, PublicationCreate
from ..services.publications import create_publication as service_create_publication
from ..services.publications import create_publication_asset as service_create_publication_asset
from ..services.publications import list_publication_assets as service_list_publication_assets
from ..services.publications import list_publications as service_list_publications
from ..services.publications import publish_publication as service_publish_publication


router = APIRouter(tags=["publications"])


@router.post("/publications")
def create_publication(body: PublicationCreate) -> JSONResponse:
    return service_create_publication(body)


@router.get("/plan-projects/{plan_project_id}/publications")
def list_publications(plan_project_id: str, status: str | None = None) -> JSONResponse:
    return service_list_publications(plan_project_id, status=status)


@router.post("/publications/{publication_id}/publish")
def publish_publication(publication_id: str) -> JSONResponse:
    return service_publish_publication(publication_id)


@router.post("/publications/{publication_id}/assets")
def create_publication_asset(publication_id: str, body: PublicationAssetCreate) -> JSONResponse:
    payload = body.model_dump()
    payload["publication_id"] = publication_id
    return service_create_publication_asset(PublicationAssetCreate(**payload))


@router.get("/publications/{publication_id}/assets")
def list_publication_assets(publication_id: str) -> JSONResponse:
    return service_list_publication_assets(publication_id)
