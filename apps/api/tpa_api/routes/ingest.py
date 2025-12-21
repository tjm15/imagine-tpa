from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.ingest import AuthorityPackIngestRequest
from ..services.ingest import get_ingest_batch as service_get_ingest_batch
from ..services.ingest import get_document_coverage as service_get_document_coverage
from ..services.ingest import get_ingest_job as service_get_ingest_job
from ..services.ingest import ingest_authority_pack as service_ingest_authority_pack
from ..services.ingest import list_ingest_batches as service_list_ingest_batches
from ..services.ingest import list_ingest_jobs as service_list_ingest_jobs
from ..services.ingest import start_ingest_authority_pack as service_start_ingest_authority_pack


router = APIRouter(tags=["ingest"])


@router.post("/ingest/authority-packs/{authority_id}/start")
def start_ingest_authority_pack(authority_id: str, body: AuthorityPackIngestRequest | None = None) -> JSONResponse:
    return service_start_ingest_authority_pack(authority_id, body)


@router.post("/ingest/authority-packs/{authority_id}")
def ingest_authority_pack(authority_id: str, body: AuthorityPackIngestRequest | None = None) -> JSONResponse:
    return service_ingest_authority_pack(authority_id, body)


@router.get("/ingest/batches")
def list_ingest_batches(authority_id: str | None = None, plan_cycle_id: str | None = None, limit: int = 25) -> JSONResponse:
    return service_list_ingest_batches(authority_id=authority_id, plan_cycle_id=plan_cycle_id, limit=limit)


@router.get("/ingest/jobs")
def list_ingest_jobs(
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> JSONResponse:
    return service_list_ingest_jobs(authority_id=authority_id, plan_cycle_id=plan_cycle_id, status=status, limit=limit)


@router.get("/ingest/jobs/{ingest_job_id}")
def get_ingest_job(ingest_job_id: str) -> JSONResponse:
    return service_get_ingest_job(ingest_job_id)


@router.get("/ingest/batches/{ingest_batch_id}")
def get_ingest_batch(ingest_batch_id: str) -> JSONResponse:
    return service_get_ingest_batch(ingest_batch_id)


@router.get("/ingest/documents/{document_id}/coverage")
def get_document_coverage(document_id: str, run_id: str | None = None, alias: str | None = None) -> JSONResponse:
    return service_get_document_coverage(document_id=document_id, run_id=run_id, alias=alias)
