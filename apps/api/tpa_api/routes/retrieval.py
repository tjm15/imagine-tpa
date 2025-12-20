from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.retrieval import RetrieveChunksRequest, RetrievePolicyClausesRequest
from ..services.retrieval import retrieve_chunks as service_retrieve_chunks
from ..services.retrieval import retrieve_policy_clauses as service_retrieve_policy_clauses
from ..services.retrieval import search_chunks as service_search_chunks


router = APIRouter(tags=["retrieval"])


@router.get("/search/chunks")
def search_chunks(
    q: str,
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    active_only: bool = True,
    limit: int = 12,
) -> JSONResponse:
    return service_search_chunks(
        q=q,
        authority_id=authority_id,
        plan_cycle_id=plan_cycle_id,
        active_only=active_only,
        limit=limit,
    )


@router.post("/retrieval/chunks")
def retrieve_chunks(body: RetrieveChunksRequest) -> JSONResponse:
    return service_retrieve_chunks(body)


@router.post("/retrieval/policy-clauses")
def retrieve_policy_clauses(body: RetrievePolicyClausesRequest) -> JSONResponse:
    return service_retrieve_policy_clauses(body)
