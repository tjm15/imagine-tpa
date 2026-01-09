from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel
from fastapi.responses import JSONResponse

from ..services.debug import debug_overview as service_debug_overview
from ..services.debug import kg_snapshot as service_kg_snapshot
from ..services.debug import list_documents as service_list_documents
from ..services.debug import list_ingest_run_steps as service_list_ingest_run_steps
from ..services.debug import list_ingest_runs as service_list_ingest_runs
from ..services.debug import list_prompts as service_list_prompts
from ..services.debug import list_runs as service_list_runs
from ..services.debug import run_latest_moves as service_run_latest_moves
from ..services.debug import get_tool_run as service_get_tool_run
from ..services.debug import list_tool_runs as service_list_tool_runs
from ..services.debug import list_visual_assets as service_list_visual_assets
from ..services.debug import visual_asset_detail as service_visual_asset_detail
from ..services.debug import assemble_context_pack as service_assemble_context_pack
from ..services.debug import retrieve_spatial_features as service_retrieve_spatial_features
from ..services.debug import retrieve_visual_assets as service_retrieve_visual_assets


router = APIRouter(tags=["debug"])


class DebugIngestReset(BaseModel):
    scope: Literal["running", "all"] = "running"
    ingest_job_id: str | None = None
    run_id: str | None = None
    ingest_batch_id: str | None = None
    authority_id: str | None = None
    plan_cycle_id: str | None = None
    note: str | None = None


class DebugIngestRequeue(BaseModel):
    ingest_job_id: str
    note: str | None = None


class DebugIngestGraph(BaseModel):
    ingest_job_id: str
    note: str | None = None


class DebugContextPackAssemble(BaseModel):
    run_id: str
    move_type: str
    work_mode: str = "plan_studio"
    authority_id: str | None = None
    plan_cycle_id: str | None = None
    plan_project_id: str | None = None
    scenario_id: str | None = None
    application_id: str | None = None
    token_budget: int | None = None
    framing: dict[str, Any] | None = None
    issues: list[dict[str, Any]] | None = None


class DebugRetrievalRequest(BaseModel):
    query: str
    limit: int | None = 12
    authority_id: str | None = None
    plan_cycle_id: str | None = None


@router.get("/debug/overview")
def debug_overview() -> JSONResponse:
    return service_debug_overview()


@router.get("/debug/ingest/runs")
def list_ingest_runs(authority_id: str | None = None, plan_cycle_id: str | None = None, limit: int = 25) -> JSONResponse:
    return service_list_ingest_runs(authority_id=authority_id, plan_cycle_id=plan_cycle_id, limit=limit)


@router.get("/debug/ingest/run-steps")
def list_ingest_run_steps(run_id: str) -> JSONResponse:
    return service_list_ingest_run_steps(run_id)


@router.get("/debug/documents")
def list_documents(
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    run_id: str | None = None,
    limit: int = 50,
) -> JSONResponse:
    return service_list_documents(authority_id=authority_id, plan_cycle_id=plan_cycle_id, run_id=run_id, limit=limit)


@router.get("/debug/tool-runs")
def list_tool_runs(
    limit: int = 50,
    tool_name: str | None = None,
    run_id: str | None = None,
    ingest_batch_id: str | None = None,
) -> JSONResponse:
    return service_list_tool_runs(limit=limit, tool_name=tool_name, run_id=run_id, ingest_batch_id=ingest_batch_id)


@router.get("/debug/tool-runs/{tool_run_id}")
def get_tool_run(tool_run_id: str) -> JSONResponse:
    return service_get_tool_run(tool_run_id)


@router.post("/debug/context-packs/assemble")
def debug_context_pack_assemble(body: DebugContextPackAssemble) -> JSONResponse:
    return service_assemble_context_pack(
        run_id=body.run_id,
        move_type=body.move_type,
        work_mode=body.work_mode,
        authority_id=body.authority_id,
        plan_cycle_id=body.plan_cycle_id,
        plan_project_id=body.plan_project_id,
        scenario_id=body.scenario_id,
        application_id=body.application_id,
        token_budget=body.token_budget,
        framing=body.framing,
        issues=body.issues or [],
    )


@router.post("/debug/retrieval/visual-assets")
def debug_retrieve_visual_assets(body: DebugRetrievalRequest) -> JSONResponse:
    return service_retrieve_visual_assets(
        query=body.query,
        limit=body.limit or 12,
        authority_id=body.authority_id,
        plan_cycle_id=body.plan_cycle_id,
    )


@router.post("/debug/retrieval/spatial-features")
def debug_retrieve_spatial_features(body: DebugRetrievalRequest) -> JSONResponse:
    return service_retrieve_spatial_features(
        query=body.query,
        limit=body.limit or 12,
        authority_id=body.authority_id,
    )


@router.get("/debug/visual-assets")
def list_visual_assets(
    limit: int = 50,
    document_id: str | None = None,
    run_id: str | None = None,
) -> JSONResponse:
    return service_list_visual_assets(limit=limit, document_id=document_id, run_id=run_id)


@router.get("/debug/visual-assets/{visual_asset_id}")
def visual_asset_detail(visual_asset_id: str) -> JSONResponse:
    return service_visual_asset_detail(visual_asset_id)


@router.get("/debug/prompts")
def list_prompts() -> JSONResponse:
    return service_list_prompts()


@router.get("/debug/runs")
def list_runs(limit: int = 25) -> JSONResponse:
    return service_list_runs(limit=limit)


@router.get("/debug/runs/{run_id}/latest-moves")
def debug_run_latest_moves(run_id: str) -> JSONResponse:
    return service_run_latest_moves(run_id)


@router.get("/debug/kg")
def kg_snapshot(limit: int = 500, edge_limit: int = 2000, node_type: str | None = None, edge_type: str | None = None) -> JSONResponse:
    return service_kg_snapshot(limit=limit, edge_limit=edge_limit, node_type=node_type, edge_type=edge_type)


@router.get("/debug/policies/{document_id}")
def debug_policies(document_id: str) -> JSONResponse:
    from ..services.debug import debug_policies as service_debug_policies
    return service_debug_policies(document_id)


@router.get("/debug/ingest/runs/{run_id}/deep")
def debug_ingest_run_deep(run_id: str) -> JSONResponse:
    from ..services.debug import debug_ingest_run_deep as service_debug_ingest_run_deep
    return service_debug_ingest_run_deep(run_id)


@router.post("/debug/ingest/upload")
async def debug_upload_ingest(file: UploadFile) -> JSONResponse:
    from ..services.debug import upload_and_ingest_file as service_upload_and_ingest_file
    content = await file.read()
    return service_upload_and_ingest_file(content, file.filename or "debug_doc.pdf")


@router.post("/debug/ingest/reset")
def debug_reset_ingest(body: DebugIngestReset) -> JSONResponse:
    from ..services.debug import reset_ingest_state as service_reset_ingest_state

    return service_reset_ingest_state(
        scope=body.scope,
        ingest_job_id=body.ingest_job_id,
        run_id=body.run_id,
        ingest_batch_id=body.ingest_batch_id,
        authority_id=body.authority_id,
        plan_cycle_id=body.plan_cycle_id,
        note=body.note,
    )


@router.post("/debug/ingest/reset-stale")
def debug_reset_stale(max_age_hours: float = 2.0, note: str | None = None) -> JSONResponse:
    from ..services.debug import reset_stale_ingest_runs as service_reset_stale_ingest_runs

    return service_reset_stale_ingest_runs(max_age_hours=max_age_hours, note=note)


@router.post("/debug/ingest/requeue")
def debug_requeue_ingest(body: DebugIngestRequeue) -> JSONResponse:
    from ..services.debug import requeue_ingest_job as service_requeue_ingest_job

    return service_requeue_ingest_job(body.ingest_job_id, note=body.note)


@router.post("/debug/ingest/run-graph")
def debug_run_graph_ingest(body: DebugIngestGraph) -> JSONResponse:
    from ..services.debug import run_graph_ingest_job as service_run_graph_ingest_job

    return service_run_graph_ingest_job(body.ingest_job_id, note=body.note)
