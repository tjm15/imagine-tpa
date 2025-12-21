from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.consultations import ConsultationCreate, ConsultationPatch
from ..services.consultations import ConsultationSummaryCreate, IssueClusterCreate
from ..services.consultations import InviteeCreate, RepresentationCreate
from ..services.consultations import create_consultation as service_create_consultation
from ..services.consultations import create_consultation_summary as service_create_consultation_summary
from ..services.consultations import create_issue_cluster as service_create_issue_cluster
from ..services.consultations import create_invitee as service_create_invitee
from ..services.consultations import create_representation as service_create_representation
from ..services.consultations import list_consultation_summaries as service_list_consultation_summaries
from ..services.consultations import list_consultations as service_list_consultations
from ..services.consultations import list_issue_clusters as service_list_issue_clusters
from ..services.consultations import list_invitees as service_list_invitees
from ..services.consultations import list_representations as service_list_representations
from ..services.consultations import patch_consultation as service_patch_consultation
from ..services.consultations import publish_consultation_summary as service_publish_consultation_summary


router = APIRouter(tags=["consultations"])


@router.post("/consultations")
def create_consultation(body: ConsultationCreate) -> JSONResponse:
    return service_create_consultation(body)


@router.get("/plan-projects/{plan_project_id}/consultations")
def list_consultations(plan_project_id: str) -> JSONResponse:
    return service_list_consultations(plan_project_id)


@router.patch("/consultations/{consultation_id}")
def patch_consultation(consultation_id: str, body: ConsultationPatch) -> JSONResponse:
    return service_patch_consultation(consultation_id, body)


@router.post("/consultations/{consultation_id}/invitees")
def create_invitee(consultation_id: str, body: InviteeCreate) -> JSONResponse:
    payload = body.model_dump()
    payload["consultation_id"] = consultation_id
    return service_create_invitee(InviteeCreate(**payload))


@router.get("/consultations/{consultation_id}/invitees")
def list_invitees(consultation_id: str) -> JSONResponse:
    return service_list_invitees(consultation_id)


@router.post("/consultations/{consultation_id}/representations")
def create_representation(consultation_id: str, body: RepresentationCreate) -> JSONResponse:
    payload = body.model_dump()
    payload["consultation_id"] = consultation_id
    return service_create_representation(RepresentationCreate(**payload))


@router.get("/consultations/{consultation_id}/representations")
def list_representations(consultation_id: str) -> JSONResponse:
    return service_list_representations(consultation_id)


@router.post("/consultations/{consultation_id}/summaries")
def create_consultation_summary(consultation_id: str, body: ConsultationSummaryCreate) -> JSONResponse:
    payload = body.model_dump()
    payload["consultation_id"] = consultation_id
    return service_create_consultation_summary(ConsultationSummaryCreate(**payload))


@router.get("/consultations/{consultation_id}/summaries")
def list_consultation_summaries(consultation_id: str) -> JSONResponse:
    return service_list_consultation_summaries(consultation_id)


@router.post("/consultation-summaries/{summary_id}/publish")
def publish_consultation_summary(summary_id: str) -> JSONResponse:
    return service_publish_consultation_summary(summary_id)


@router.post("/consultations/{consultation_id}/issue-clusters")
def create_issue_cluster(consultation_id: str, body: IssueClusterCreate) -> JSONResponse:
    payload = body.model_dump()
    payload["consultation_id"] = consultation_id
    return service_create_issue_cluster(IssueClusterCreate(**payload))


@router.get("/consultations/{consultation_id}/issue-clusters")
def list_issue_clusters(consultation_id: str) -> JSONResponse:
    return service_list_issue_clusters(consultation_id)
