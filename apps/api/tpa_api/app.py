from __future__ import annotations

from fastapi import FastAPI

from .db import init_db_pool, shutdown_db_pool
from .routes.core import router as core_router
from .routes.draft import router as draft_router
from .routes.ingest import router as ingest_router
from .routes.plan_cycles import router as plan_cycles_router
from .routes.plan_projects import router as plan_projects_router
from .routes.retrieval import router as retrieval_router
from .routes.retrieval_frames import router as retrieval_frames_router
from .routes.scenarios import router as scenarios_router
from .routes.spec import router as spec_router
from .routes.tool_requests import router as tool_requests_router
from .routes.trace import router as trace_router


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
    app.include_router(plan_cycles_router)
    app.include_router(plan_projects_router)
    app.include_router(scenarios_router)
    app.include_router(trace_router)
    app.include_router(retrieval_router)
    app.include_router(retrieval_frames_router)
    app.include_router(tool_requests_router)
    app.include_router(ingest_router)

    return app


# Docker uses `tpa_api.main:app` as a stable entrypoint; `tpa_api.main` re-exports this app.
app = create_app()
