from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..db import _db_fetch_all, _db_fetch_one
from ..time_utils import _utc_now_iso


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    row = _db_fetch_one(sql, params)
    if not row:
        return 0
    return int(row.get("count") or 0)


def debug_overview() -> JSONResponse:
    counts = {
        "ingest_batches": _count("SELECT COUNT(*) AS count FROM ingest_batches"),
        "ingest_runs": _count("SELECT COUNT(*) AS count FROM ingest_runs"),
        "ingest_run_steps": _count("SELECT COUNT(*) AS count FROM ingest_run_steps"),
        "documents": _count("SELECT COUNT(*) AS count FROM documents"),
        "pages": _count("SELECT COUNT(*) AS count FROM pages"),
        "layout_blocks": _count("SELECT COUNT(*) AS count FROM layout_blocks"),
        "chunks": _count("SELECT COUNT(*) AS count FROM chunks"),
        "visual_assets": _count("SELECT COUNT(*) AS count FROM visual_assets"),
        "visual_asset_regions": _count("SELECT COUNT(*) AS count FROM visual_asset_regions"),
        "segmentation_masks": _count("SELECT COUNT(*) AS count FROM segmentation_masks"),
        "visual_semantic_outputs": _count("SELECT COUNT(*) AS count FROM visual_semantic_outputs"),
        "policy_sections": _count("SELECT COUNT(*) AS count FROM policy_sections"),
        "policy_clauses": _count("SELECT COUNT(*) AS count FROM policy_clauses"),
        "unit_embeddings": _count("SELECT COUNT(*) AS count FROM unit_embeddings"),
        "tool_runs": _count("SELECT COUNT(*) AS count FROM tool_runs"),
        "prompts": _count("SELECT COUNT(*) AS count FROM prompts"),
        "prompt_versions": _count("SELECT COUNT(*) AS count FROM prompt_versions"),
        "kg_nodes": _count("SELECT COUNT(*) AS count FROM kg_node"),
        "kg_edges": _count("SELECT COUNT(*) AS count FROM kg_edge"),
        "runs": _count("SELECT COUNT(*) AS count FROM runs"),
        "move_events": _count("SELECT COUNT(*) AS count FROM move_events"),
    }
    return JSONResponse(content=jsonable_encoder({"counts": counts, "generated_at": _utc_now_iso()}))


def list_ingest_runs(authority_id: str | None = None, plan_cycle_id: str | None = None, limit: int = 25) -> JSONResponse:
    clauses: list[str] = []
    params: list[Any] = []
    if authority_id:
        clauses.append("authority_id = %s")
        params.append(authority_id)
    if plan_cycle_id:
        clauses.append("plan_cycle_id = %s::uuid")
        params.append(plan_cycle_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = _db_fetch_all(
        f"""
        SELECT id, ingest_batch_id, authority_id, plan_cycle_id, pipeline_version,
               status, started_at, ended_at
        FROM ingest_runs
        {where}
        ORDER BY started_at DESC
        LIMIT %s
        """,
        tuple(params),
    )
    return JSONResponse(content=jsonable_encoder({"ingest_runs": rows}))


def list_ingest_run_steps(run_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, ingest_batch_id, run_id, step_name, status, started_at, ended_at, error_text,
               inputs_jsonb, outputs_jsonb
        FROM ingest_run_steps
        WHERE run_id = %s::uuid
        ORDER BY started_at ASC NULLS LAST
        """,
        (run_id,),
    )
    return JSONResponse(content=jsonable_encoder({"run_id": run_id, "steps": rows}))


def list_documents(authority_id: str | None = None, plan_cycle_id: str | None = None, limit: int = 50) -> JSONResponse:
    clauses: list[str] = []
    params: list[Any] = []
    if authority_id:
        clauses.append("authority_id = %s")
        params.append(authority_id)
    if plan_cycle_id:
        clauses.append("plan_cycle_id = %s::uuid")
        params.append(plan_cycle_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = _db_fetch_all(
        f"""
        SELECT id, authority_id, plan_cycle_id, run_id,
               COALESCE(metadata->>'title', metadata->>'document_title', metadata->>'name', '') AS title,
               raw_blob_path, raw_sha256, raw_bytes, raw_source_uri, created_at
        FROM documents
        {where}
        ORDER BY created_at DESC
        LIMIT %s
        """,
        tuple(params),
    )
    return JSONResponse(content=jsonable_encoder({"documents": rows}))


def list_tool_runs(
    limit: int = 50,
    tool_name: str | None = None,
    run_id: str | None = None,
    ingest_batch_id: str | None = None,
) -> JSONResponse:
    clauses: list[str] = []
    params: list[Any] = []
    if tool_name:
        clauses.append("tool_name = %s")
        params.append(tool_name)
    if run_id:
        clauses.append("run_id = %s::uuid")
        params.append(run_id)
    if ingest_batch_id:
        clauses.append("ingest_batch_id = %s::uuid")
        params.append(ingest_batch_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = _db_fetch_all(
        f"""
        SELECT id, ingest_batch_id, run_id, tool_name, status, started_at, ended_at,
               confidence_hint, uncertainty_note, inputs_logged, outputs_logged
        FROM tool_runs
        {where}
        ORDER BY started_at DESC NULLS LAST
        LIMIT %s
        """,
        tuple(params),
    )
    return JSONResponse(content=jsonable_encoder({"tool_runs": rows}))


def list_prompts() -> JSONResponse:
    prompts = _db_fetch_all(
        """
        SELECT prompt_id, name, purpose, created_at, created_by
        FROM prompts
        ORDER BY prompt_id ASC
        """
    )
    versions = _db_fetch_all(
        """
        SELECT prompt_id, prompt_version, input_schema_ref, output_schema_ref, created_at, created_by
        FROM prompt_versions
        ORDER BY prompt_id ASC, prompt_version DESC
        """
    )
    return JSONResponse(content=jsonable_encoder({"prompts": prompts, "prompt_versions": versions}))


def list_runs(limit: int = 25) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, profile, culp_stage_id, created_at
        FROM runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return JSONResponse(content=jsonable_encoder({"runs": rows}))


def kg_snapshot(limit: int = 500, edge_limit: int = 2000, node_type: str | None = None, edge_type: str | None = None) -> JSONResponse:
    clauses: list[str] = []
    params: list[Any] = []
    if node_type:
        clauses.append("node_type = %s")
        params.append(node_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    nodes = _db_fetch_all(
        f"""
        SELECT node_id, node_type, props_jsonb, canonical_fk
        FROM kg_node
        {where}
        ORDER BY node_id ASC
        LIMIT %s
        """,
        tuple(params),
    )
    node_ids = [row["node_id"] for row in nodes]
    edges: list[dict[str, Any]] = []
    if node_ids:
        edge_clauses: list[str] = ["src_id = ANY(%s::uuid[])", "dst_id = ANY(%s::uuid[])"]
        edge_params: list[Any] = [node_ids, node_ids]
        if edge_type:
            edge_clauses.append("edge_type = %s")
            edge_params.append(edge_type)
        edge_params.append(edge_limit)
        edges = _db_fetch_all(
            f"""
            SELECT edge_id, src_id, dst_id, edge_type, props_jsonb, evidence_ref_id, tool_run_id
            FROM kg_edge
            WHERE {' AND '.join(edge_clauses)}
            ORDER BY edge_id ASC
            LIMIT %s
            """,
            tuple(edge_params),
        )
    return JSONResponse(content=jsonable_encoder({"nodes": nodes, "edges": edges}))
