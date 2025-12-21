from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.visuals import get_visual_asset_blob as service_get_visual_asset_blob
from ..services.visuals import list_visual_assets as service_list_visual_assets
from ..services.visuals import list_visual_features as service_list_visual_features


router = APIRouter(tags=["visuals"])


@router.get("/visual-assets")
def list_visual_assets(
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    document_id: str | None = None,
    plan_project_id: str | None = None,
    limit: int = 80,
) -> JSONResponse:
    return service_list_visual_assets(
        authority_id=authority_id,
        plan_cycle_id=plan_cycle_id,
        document_id=document_id,
        plan_project_id=plan_project_id,
        limit=limit,
    )


@router.get("/visual-assets/{visual_asset_id}/features")
def list_visual_features(visual_asset_id: str) -> JSONResponse:
    return service_list_visual_features(visual_asset_id)


@router.get("/visual-assets/{visual_asset_id}/blob")
def get_visual_asset_blob(visual_asset_id: str) -> JSONResponse:
    return service_get_visual_asset_blob(visual_asset_id)
