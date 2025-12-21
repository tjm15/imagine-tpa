from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.site_selection import AllocationDecisionCreate, DecisionLogCreate, MitigationCreate
from ..services.site_selection import SiteAssessmentCreate, SiteCategoryCreate, SiteCreate, SiteScoreCreate
from ..services.site_selection import Stage4SummaryRowCreate
from ..services.site_selection import create_allocation_decision as service_create_allocation_decision
from ..services.site_selection import create_decision_log as service_create_decision_log
from ..services.site_selection import create_mitigation as service_create_mitigation
from ..services.site_selection import create_site_assessment as service_create_site_assessment
from ..services.site_selection import create_site_category as service_create_site_category
from ..services.site_selection import create_site as service_create_site
from ..services.site_selection import create_site_score as service_create_site_score
from ..services.site_selection import create_stage4_summary_row as service_create_stage4_summary_row
from ..services.site_selection import list_allocation_decisions as service_list_allocation_decisions
from ..services.site_selection import list_decision_logs as service_list_decision_logs
from ..services.site_selection import list_mitigations as service_list_mitigations
from ..services.site_selection import list_site_assessments as service_list_site_assessments
from ..services.site_selection import list_site_categories as service_list_site_categories
from ..services.site_selection import list_sites as service_list_sites
from ..services.site_selection import list_site_scores as service_list_site_scores
from ..services.site_selection import list_stage4_summary_rows as service_list_stage4_summary_rows


router = APIRouter(tags=["site-selection"])


@router.post("/site-categories")
def create_site_category(body: SiteCategoryCreate) -> JSONResponse:
    return service_create_site_category(body)


@router.post("/sites")
def create_site(body: SiteCreate) -> JSONResponse:
    return service_create_site(body)


@router.get("/sites")
def list_sites(limit: int = 50) -> JSONResponse:
    return service_list_sites(limit=limit)


@router.get("/plan-projects/{plan_project_id}/site-categories")
def list_site_categories(plan_project_id: str) -> JSONResponse:
    return service_list_site_categories(plan_project_id)


@router.post("/site-assessments")
def create_site_assessment(body: SiteAssessmentCreate) -> JSONResponse:
    return service_create_site_assessment(body)


@router.get("/plan-projects/{plan_project_id}/site-assessments")
def list_site_assessments(plan_project_id: str, stage: str | None = None) -> JSONResponse:
    return service_list_site_assessments(plan_project_id, stage=stage)


@router.post("/site-scores")
def create_site_score(body: SiteScoreCreate) -> JSONResponse:
    return service_create_site_score(body)


@router.get("/site-assessments/{site_assessment_id}/site-scores")
def list_site_scores(site_assessment_id: str) -> JSONResponse:
    return service_list_site_scores(site_assessment_id)


@router.post("/mitigations")
def create_mitigation(body: MitigationCreate) -> JSONResponse:
    return service_create_mitigation(body)


@router.get("/site-assessments/{site_assessment_id}/mitigations")
def list_mitigations(site_assessment_id: str) -> JSONResponse:
    return service_list_mitigations(site_assessment_id)


@router.post("/allocation-decisions")
def create_allocation_decision(body: AllocationDecisionCreate) -> JSONResponse:
    return service_create_allocation_decision(body)


@router.get("/plan-projects/{plan_project_id}/allocation-decisions")
def list_allocation_decisions(plan_project_id: str) -> JSONResponse:
    return service_list_allocation_decisions(plan_project_id)


@router.post("/decision-logs")
def create_decision_log(body: DecisionLogCreate) -> JSONResponse:
    return service_create_decision_log(body)


@router.get("/allocation-decisions/{allocation_decision_id}/decision-logs")
def list_decision_logs(allocation_decision_id: str) -> JSONResponse:
    return service_list_decision_logs(allocation_decision_id)


@router.post("/stage4-summary-rows")
def create_stage4_summary_row(body: Stage4SummaryRowCreate) -> JSONResponse:
    return service_create_stage4_summary_row(body)


@router.get("/plan-projects/{plan_project_id}/stage4-summary-rows")
def list_stage4_summary_rows(plan_project_id: str) -> JSONResponse:
    return service_list_stage4_summary_rows(plan_project_id)
