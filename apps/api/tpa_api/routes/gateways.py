from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.gateways import GatewayOutcomeCreate, GatewaySubmissionCreate, StatementCreate
from ..services.gateways import create_gateway_outcome as service_create_gateway_outcome
from ..services.gateways import create_gateway_submission as service_create_gateway_submission
from ..services.gateways import create_readiness_for_exam as service_create_readiness_for_exam
from ..services.gateways import create_statement_compliance as service_create_statement_compliance
from ..services.gateways import create_statement_soundness as service_create_statement_soundness
from ..services.gateways import list_gateway_outcomes as service_list_gateway_outcomes
from ..services.gateways import list_gateway_submissions as service_list_gateway_submissions
from ..services.gateways import list_statements as service_list_statements


router = APIRouter(tags=["gateways"])


@router.post("/gateways/submissions")
def create_gateway_submission(body: GatewaySubmissionCreate) -> JSONResponse:
    return service_create_gateway_submission(body)


@router.get("/plan-projects/{plan_project_id}/gateways/submissions")
def list_gateway_submissions(plan_project_id: str) -> JSONResponse:
    return service_list_gateway_submissions(plan_project_id)


@router.post("/gateways/outcomes")
def create_gateway_outcome(body: GatewayOutcomeCreate) -> JSONResponse:
    return service_create_gateway_outcome(body)


@router.get("/gateways/submissions/{gateway_submission_id}/outcomes")
def list_gateway_outcomes(gateway_submission_id: str) -> JSONResponse:
    return service_list_gateway_outcomes(gateway_submission_id)


@router.post("/gateways/statements/compliance")
def create_statement_compliance(body: StatementCreate) -> JSONResponse:
    return service_create_statement_compliance(body)


@router.post("/gateways/statements/soundness")
def create_statement_soundness(body: StatementCreate) -> JSONResponse:
    return service_create_statement_soundness(body)


@router.post("/gateways/statements/readiness")
def create_readiness_statement(body: StatementCreate) -> JSONResponse:
    return service_create_readiness_for_exam(body)


@router.get("/plan-projects/{plan_project_id}/gateways/statements/compliance")
def list_statements_compliance(plan_project_id: str) -> JSONResponse:
    return service_list_statements("statement_compliance", plan_project_id)


@router.get("/plan-projects/{plan_project_id}/gateways/statements/soundness")
def list_statements_soundness(plan_project_id: str) -> JSONResponse:
    return service_list_statements("statement_soundness", plan_project_id)


@router.get("/plan-projects/{plan_project_id}/gateways/statements/readiness")
def list_statements_readiness(plan_project_id: str) -> JSONResponse:
    return service_list_statements("readiness_for_exam", plan_project_id)
