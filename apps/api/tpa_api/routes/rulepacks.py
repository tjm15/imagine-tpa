from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.rulepacks import get_rule_pack_version as service_get_rule_pack_version
from ..services.rulepacks import install_default_rule_pack as service_install_default_rule_pack
from ..services.rulepacks import list_rule_pack_versions as service_list_rule_pack_versions
from ..services.rulepacks import list_rule_packs as service_list_rule_packs


router = APIRouter(tags=["rule-packs"])


@router.post("/rule-packs/install-default")
def install_default_rule_pack() -> JSONResponse:
    return service_install_default_rule_pack()


@router.get("/rule-packs")
def list_rule_packs() -> JSONResponse:
    return service_list_rule_packs()


@router.get("/rule-packs/{rule_pack_key}/versions")
def list_rule_pack_versions(rule_pack_key: str) -> JSONResponse:
    return service_list_rule_pack_versions(rule_pack_key)


@router.get("/rule-pack-versions/{rule_pack_version_id}")
def get_rule_pack_version(rule_pack_version_id: str) -> JSONResponse:
    return service_get_rule_pack_version(rule_pack_version_id)
