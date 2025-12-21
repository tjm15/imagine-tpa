from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.evidence_graph import EvidenceGapCreate, EvidenceItemCreate, TraceLinkCreate
from ..services.evidence_graph import create_evidence_gap as service_create_evidence_gap
from ..services.evidence_graph import create_evidence_item as service_create_evidence_item
from ..services.evidence_graph import create_trace_link as service_create_trace_link
from ..services.evidence_graph import list_evidence_gaps as service_list_evidence_gaps
from ..services.evidence_graph import list_evidence_items as service_list_evidence_items
from ..services.evidence_graph import list_trace_links as service_list_trace_links


router = APIRouter(tags=["evidence"])


@router.post("/evidence/items")
def create_evidence_item(body: EvidenceItemCreate) -> JSONResponse:
    return service_create_evidence_item(body)


@router.get("/plan-projects/{plan_project_id}/evidence/items")
def list_evidence_items(plan_project_id: str) -> JSONResponse:
    return service_list_evidence_items(plan_project_id)


@router.post("/evidence/gaps")
def create_evidence_gap(body: EvidenceGapCreate) -> JSONResponse:
    return service_create_evidence_gap(body)


@router.get("/plan-projects/{plan_project_id}/evidence/gaps")
def list_evidence_gaps(plan_project_id: str) -> JSONResponse:
    return service_list_evidence_gaps(plan_project_id)


@router.post("/evidence/trace-links")
def create_trace_link(body: TraceLinkCreate) -> JSONResponse:
    return service_create_trace_link(body)


@router.get("/evidence/trace-links")
def list_trace_links(
    from_type: str | None = None,
    from_id: str | None = None,
    to_type: str | None = None,
    to_id: str | None = None,
) -> JSONResponse:
    return service_list_trace_links(from_type=from_type, from_id=from_id, to_type=to_type, to_id=to_id)
