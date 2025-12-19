from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

# Transitional router: reuse the legacy ingestion implementation while the monolith is being decomposed.
# This keeps the OSS stack working end-to-end while we migrate the ingest code into dedicated service modules.
from ..main_legacy import (  # noqa: PLC0415
    AuthorityPackIngestRequest as LegacyAuthorityPackIngestRequest,
    get_ingest_batch as legacy_get_ingest_batch,
    ingest_authority_pack as legacy_ingest_authority_pack,
    list_ingest_batches as legacy_list_ingest_batches,
    start_ingest_authority_pack as legacy_start_ingest_authority_pack,
)


router = APIRouter(tags=["ingest"])


@router.post("/ingest/authority-packs/{authority_id}/start")
def start_ingest_authority_pack(authority_id: str, body: LegacyAuthorityPackIngestRequest | None = None) -> JSONResponse:
    return legacy_start_ingest_authority_pack(authority_id, body)


@router.post("/ingest/authority-packs/{authority_id}")
def ingest_authority_pack(authority_id: str, body: LegacyAuthorityPackIngestRequest | None = None) -> JSONResponse:
    return legacy_ingest_authority_pack(authority_id, body)


@router.get("/ingest/batches")
def list_ingest_batches(authority_id: str | None = None, plan_cycle_id: str | None = None, limit: int = 25) -> JSONResponse:
    return legacy_list_ingest_batches(authority_id=authority_id, plan_cycle_id=plan_cycle_id, limit=limit)


@router.get("/ingest/batches/{ingest_batch_id}")
def get_ingest_batch(ingest_batch_id: str) -> JSONResponse:
    return legacy_get_ingest_batch(ingest_batch_id)

