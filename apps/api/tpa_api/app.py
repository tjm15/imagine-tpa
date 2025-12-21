from __future__ import annotations

from fastapi import FastAPI

from .db import init_db_pool, shutdown_db_pool
from .routes.core import router as core_router
from .routes.culp_artefacts import router as culp_artefacts_router
from .routes.consultations import router as consultations_router
from .routes.draft import router as draft_router
from .routes.evidence_graph import router as evidence_router
from .routes.examination import router as examination_router
from .routes.gateways import router as gateways_router
from .routes.ingest import router as ingest_router
from .routes.monitoring import router as monitoring_router
from .routes.applications import router as applications_router
from .routes.plan_cycles import router as plan_cycles_router
from .routes.plan_projects import router as plan_projects_router
from .routes.publications import router as publications_router
from .routes.retrieval import router as retrieval_router
from .routes.retrieval_frames import router as retrieval_frames_router
from .routes.runs import router as runs_router
from .routes.rulepacks import router as rulepacks_router
from .routes.scenarios import router as scenarios_router
from .routes.spec import router as spec_router
from .routes.site_selection import router as site_selection_router
from .routes.timetable import router as timetable_router
from .routes.tool_requests import router as tool_requests_router
from .routes.trace import router as trace_router
from .routes.workflow import router as workflow_router


def create_app() -> FastAPI:
    app = FastAPI(title="TPA API (Scaffold)", version="0.0.0")

    @app.on_event("startup")
    def _startup_db_pool() -> None:
        init_db_pool()

    @app.on_event("shutdown")
    def _shutdown_db_pool() -> None:
        shutdown_db_pool()

    app.include_router(core_router)
    app.include_router(spec_router)
    app.include_router(draft_router)
    app.include_router(rulepacks_router)
    app.include_router(workflow_router)
    app.include_router(plan_cycles_router)
    app.include_router(plan_projects_router)
    app.include_router(culp_artefacts_router)
    app.include_router(timetable_router)
    app.include_router(consultations_router)
    app.include_router(evidence_router)
    app.include_router(site_selection_router)
    app.include_router(gateways_router)
    app.include_router(examination_router)
    app.include_router(publications_router)
    app.include_router(applications_router)
    app.include_router(monitoring_router)
    app.include_router(scenarios_router)
    app.include_router(trace_router)
    app.include_router(retrieval_router)
    app.include_router(retrieval_frames_router)
    app.include_router(runs_router)
    app.include_router(tool_requests_router)
    app.include_router(ingest_router)

    return app


# Docker uses `tpa_api.main:app` as a stable entrypoint; `tpa_api.main` re-exports this app.
app = create_app()
