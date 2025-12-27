from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..api_utils import validate_uuid_or_400 as _validate_uuid_or_400
from ..db import _db_execute, _db_fetch_all, _db_fetch_one
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
        "document_identity_status": _count("SELECT COUNT(*) AS count FROM document_identity_status"),
        "pages": _count("SELECT COUNT(*) AS count FROM pages"),
        "layout_blocks": _count("SELECT COUNT(*) AS count FROM layout_blocks"),
        "chunks": _count("SELECT COUNT(*) AS count FROM chunks"),
        "visual_assets": _count("SELECT COUNT(*) AS count FROM visual_assets"),
        "visual_asset_regions": _count("SELECT COUNT(*) AS count FROM visual_asset_regions"),
        "segmentation_masks": _count("SELECT COUNT(*) AS count FROM segmentation_masks"),
        "visual_semantic_outputs": _count("SELECT COUNT(*) AS count FROM visual_semantic_outputs"),
        "transforms": _count("SELECT COUNT(*) AS count FROM transforms"),
        "projection_artifacts": _count("SELECT COUNT(*) AS count FROM projection_artifacts"),
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


def list_documents(
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    run_id: str | None = None,
    limit: int = 50,
) -> JSONResponse:
    clauses: list[str] = []
    params: list[Any] = []
    if authority_id:
        clauses.append("authority_id = %s")
        params.append(authority_id)
    if plan_cycle_id:
        clauses.append("plan_cycle_id = %s::uuid")
        params.append(_validate_uuid_or_400(plan_cycle_id, field_name="plan_cycle_id"))
    if run_id:
        clauses.append("run_id = %s::uuid")
        params.append(_validate_uuid_or_400(run_id, field_name="run_id"))
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


def list_visual_assets(
    *,
    document_id: str | None = None,
    run_id: str | None = None,
    limit: int = 50,
) -> JSONResponse:
    clauses: list[str] = []
    params: list[Any] = [run_id, run_id]
    if document_id:
        clauses.append("va.document_id = %s::uuid")
        params.append(document_id)
    if run_id:
        clauses.append("va.run_id = %s::uuid")
        params.append(run_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = _db_fetch_all(
        f"""
        SELECT
          va.id,
          va.document_id,
          va.page_number,
          va.asset_type,
          va.blob_path,
          va.metadata AS metadata_jsonb,
          va.created_at,
          vs.asset_type AS semantic_asset_type,
          vs.asset_subtype AS semantic_asset_subtype,
          COALESCE(jsonb_array_length(vs.assertions_jsonb), 0) AS assertion_count,
          (SELECT COUNT(*) FROM segmentation_masks sm WHERE sm.visual_asset_id = va.id) AS mask_count,
          (SELECT COUNT(*) FROM visual_asset_regions vr WHERE vr.visual_asset_id = va.id) AS region_count,
          (SELECT COUNT(*) FROM visual_semantic_outputs vso WHERE vso.visual_asset_id = va.id) AS semantic_count,
          (va.metadata->>'georef_status') AS georef_status,
          (va.metadata->>'georef_tool_run_id') AS georef_tool_run_id,
          (va.metadata->>'transform_id') AS transform_id
        FROM visual_assets va
        LEFT JOIN LATERAL (
          SELECT asset_type, asset_subtype, assertions_jsonb
          FROM visual_semantic_outputs
          WHERE visual_asset_id = va.id
            AND (%s::uuid IS NULL OR run_id = %s::uuid)
          ORDER BY created_at DESC
          LIMIT 1
        ) vs ON TRUE
        {where}
        ORDER BY va.created_at DESC
        LIMIT %s
        """,
        tuple(params),
    )
    return JSONResponse(content=jsonable_encoder({"visual_assets": rows}))


def visual_asset_detail(visual_asset_id: str) -> JSONResponse:
    asset = _db_fetch_one(
        """
        SELECT id, document_id, run_id, page_number, asset_type, blob_path, evidence_ref_id,
               metadata AS metadata_jsonb, created_at
        FROM visual_assets
        WHERE id = %s::uuid
        """,
        (visual_asset_id,),
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Visual asset not found")

    semantic_outputs = _db_fetch_all(
        """
        SELECT id, run_id, schema_version, output_kind, asset_type, asset_subtype,
               canonical_facts_jsonb, asset_specific_facts_jsonb, assertions_jsonb,
               agent_findings_jsonb, material_index_jsonb, metadata_jsonb, tool_run_id, created_at
        FROM visual_semantic_outputs
        WHERE visual_asset_id = %s::uuid
        ORDER BY created_at DESC
        LIMIT 5
        """,
        (visual_asset_id,),
    )

    regions = _db_fetch_all(
        """
        SELECT id, run_id, region_type, bbox, bbox_quality, mask_id, caption_text,
               evidence_ref_id, metadata_jsonb, created_at
        FROM visual_asset_regions
        WHERE visual_asset_id = %s::uuid
        ORDER BY created_at DESC
        LIMIT 50
        """,
        (visual_asset_id,),
    )

    masks = _db_fetch_all(
        """
        SELECT id, run_id, label, bbox, bbox_quality, confidence, mask_artifact_path, created_at
        FROM segmentation_masks
        WHERE visual_asset_id = %s::uuid
        ORDER BY created_at DESC
        LIMIT 50
        """,
        (visual_asset_id,),
    )

    meta = asset.get("metadata_jsonb") if isinstance(asset.get("metadata_jsonb"), dict) else {}
    transform_id = meta.get("transform_id") if isinstance(meta.get("transform_id"), str) else None
    transform = None
    projection_artifacts: list[dict[str, Any]] = []
    if transform_id:
        transform = _db_fetch_one(
            """
            SELECT id, method, matrix, matrix_shape, uncertainty_score, control_point_ids_jsonb, metadata_jsonb, created_at
            FROM transforms
            WHERE id = %s::uuid
            """,
            (transform_id,),
        )
        projection_artifacts = _db_fetch_all(
            """
            SELECT id, artifact_type, artifact_path, metadata_jsonb, created_at
            FROM projection_artifacts
            WHERE transform_id = %s::uuid
            ORDER BY created_at DESC
            """,
            (transform_id,),
        )

    payload = {
        "visual_asset": asset,
        "semantic_outputs": semantic_outputs,
        "regions": regions,
        "masks": masks,
        "transform": transform,
        "projection_artifacts": projection_artifacts,
    }
    return JSONResponse(content=jsonable_encoder(payload))


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


def debug_policies(document_id: str) -> JSONResponse:
    sections = _db_fetch_all(
        """
        SELECT id, policy_code, title, section_path, heading_text, text, page_start, page_end
        FROM policy_sections
        WHERE document_id = %s::uuid
        ORDER BY page_start ASC, section_path ASC
        """,
        (document_id,),
    )
    section_ids = [str(s["id"]) for s in sections]

    clauses = []
    definitions = []
    targets = []
    monitoring = []
    matrices = []
    scopes = []

    if section_ids:
        clauses = _db_fetch_all(
            """
            SELECT id, policy_section_id, clause_ref, text, speech_act_jsonb, conditions_jsonb
            FROM policy_clauses
            WHERE policy_section_id = ANY(%s::uuid[])
            ORDER BY span_start ASC
            """,
            (section_ids,),
        )
        definitions = _db_fetch_all(
            """
            SELECT id, policy_section_id, term, definition_text
            FROM policy_definitions
            WHERE policy_section_id = ANY(%s::uuid[])
            """,
            (section_ids,),
        )
        targets = _db_fetch_all(
            """
            SELECT id, policy_section_id, metric, value, unit, timeframe, geography_ref, raw_text
            FROM policy_targets
            WHERE policy_section_id = ANY(%s::uuid[])
            """,
            (section_ids,),
        )
        monitoring = _db_fetch_all(
            """
            SELECT id, policy_section_id, indicator_text
            FROM policy_monitoring_hooks
            WHERE policy_section_id = ANY(%s::uuid[])
            """,
            (section_ids,),
        )
        matrices = _db_fetch_all(
            """
            SELECT id, policy_section_id, matrix_jsonb
            FROM policy_matrices
            WHERE policy_section_id = ANY(%s::uuid[])
            """,
            (section_ids,),
        )
        scopes = _db_fetch_all(
            """
            SELECT id, policy_section_id, scope_jsonb
            FROM policy_scopes
            WHERE policy_section_id = ANY(%s::uuid[])
            """,
            (section_ids,),
        )

    # Orphaned matrices/scopes (linked to document but not section)
    orphaned_matrices = _db_fetch_all(
        """
        SELECT id, policy_section_id, matrix_jsonb
        FROM policy_matrices
        WHERE document_id = %s::uuid AND policy_section_id IS NULL
        """,
        (document_id,),
    )
    matrices.extend(orphaned_matrices)

    orphaned_scopes = _db_fetch_all(
        """
        SELECT id, policy_section_id, scope_jsonb
        FROM policy_scopes
        WHERE document_id = %s::uuid AND policy_section_id IS NULL
        """,
        (document_id,),
    )
    scopes.extend(orphaned_scopes)

    return JSONResponse(
        content=jsonable_encoder(
            {
                "sections": sections,
                "clauses": clauses,
                "definitions": definitions,
                "targets": targets,
                "monitoring": monitoring,
                "matrices": matrices,
                "scopes": scopes,
            }
        )
    )


def debug_ingest_run_deep(run_id: str) -> JSONResponse:
    run = _db_fetch_one(
        """
        SELECT id, ingest_batch_id, authority_id, plan_cycle_id, status, started_at, ended_at,
               inputs_jsonb, outputs_jsonb, error_text, model_ids_jsonb
        FROM ingest_runs
        WHERE id = %s::uuid
        """,
        (run_id,),
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    steps = _db_fetch_all(
        """
        SELECT step_name, status, started_at, ended_at, error_text, inputs_jsonb, outputs_jsonb
        FROM ingest_run_steps
        WHERE run_id = %s::uuid
        ORDER BY started_at ASC
        """,
        (run_id,),
    )

    tool_runs = _db_fetch_all(
        """
        SELECT id, tool_name, status, started_at, ended_at, confidence_hint, uncertainty_note,
               inputs_logged, outputs_logged, (outputs_logged->>'error') as error_detail
        FROM tool_runs
        WHERE run_id = %s::uuid
        ORDER BY started_at ASC
        """,
        (run_id,),
    )

    # Output counts
    counts = {
        "pages": _count("SELECT COUNT(*) AS count FROM pages WHERE run_id = %s::uuid", (run_id,)),
        "layout_blocks": _count("SELECT COUNT(*) AS count FROM layout_blocks WHERE run_id = %s::uuid", (run_id,)),
        "visual_assets": _count("SELECT COUNT(*) AS count FROM visual_assets WHERE run_id = %s::uuid", (run_id,)),
        "policy_sections": _count("SELECT COUNT(*) AS count FROM policy_sections WHERE run_id = %s::uuid", (run_id,)),
        "policy_clauses": _count("SELECT COUNT(*) AS count FROM policy_clauses WHERE run_id = %s::uuid", (run_id,)),
        "matrices": _count("SELECT COUNT(*) AS count FROM policy_matrices WHERE run_id = %s::uuid", (run_id,)),
        "scopes": _count("SELECT COUNT(*) AS count FROM policy_scopes WHERE run_id = %s::uuid", (run_id,)),
        "vectors": _count("SELECT COUNT(*) AS count FROM unit_embeddings WHERE run_id = %s::uuid", (run_id,)),
    }

    return JSONResponse(
        content=jsonable_encoder(
            {
                "run": run,
                "steps": steps,
                "tool_runs": tool_runs,
                "output_counts": counts,
            }
        )
    )


def upload_and_ingest_file(file_bytes: bytes, filename: str) -> JSONResponse:
    from uuid import uuid4
    from pathlib import Path
    import os
    from ..services.ingest import _create_ingest_job, _enqueue_ingest_job
    from ..db import _db_execute

    # 1. Save file to debug pack directory
    debug_root = Path(os.environ.get("TPA_DEBUG_UPLOAD_ROOT", "/debug_uploads")).resolve()
    debug_dir = debug_root / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = debug_dir / filename
    file_path.write_bytes(file_bytes)

    # 2. Create Ingest Job
    authority_id = "debug"
    
    # Create a batch
    ingest_batch_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO ingest_batches (
          id, source_system, authority_id, status, started_at, inputs_jsonb, outputs_jsonb
        )
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
        """,
        (ingest_batch_id, "debug_upload", authority_id, "running", _utc_now_iso(), "{}", "{}"),
    )

    ingest_job_id = _create_ingest_job(
        authority_id=authority_id,
        plan_cycle_id=None,
        ingest_batch_id=ingest_batch_id,
        job_type="manual_upload",
        inputs={
            "authority_id": authority_id,
            "pack_dir": str(debug_dir),
            "documents": [
                {
                    "file_path": filename,
                    "title": filename,
                    "source": "debug_upload",
                    "document_type": "local_plan",
                }
            ],
        },
    )

    # 3. Enqueue
    enqueued, error = _enqueue_ingest_job(ingest_job_id)
    if not enqueued:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue debug job: {error}")

    return JSONResponse(content={"ingest_job_id": ingest_job_id, "ingest_batch_id": ingest_batch_id})


def reset_ingest_state(
    *,
    scope: str = "running",
    ingest_job_id: str | None = None,
    run_id: str | None = None,
    ingest_batch_id: str | None = None,
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    note: str | None = None,
) -> JSONResponse:
    scope = scope or "running"
    if scope not in {"running", "all"}:
        raise HTTPException(status_code=400, detail="scope must be one of: running, all")

    job_id = _validate_uuid_or_400(ingest_job_id, field_name="ingest_job_id") if ingest_job_id else None
    run_id_val = _validate_uuid_or_400(run_id, field_name="run_id") if run_id else None
    batch_id = _validate_uuid_or_400(ingest_batch_id, field_name="ingest_batch_id") if ingest_batch_id else None
    plan_cycle_val = _validate_uuid_or_400(plan_cycle_id, field_name="plan_cycle_id") if plan_cycle_id else None

    note_text = note or "reset via debug"

    job_clauses: list[str] = []
    job_params: list[Any] = []
    if scope == "running":
        job_clauses.append("status IN ('running', 'pending')")
    if job_id:
        job_clauses.append("id = %s::uuid")
        job_params.append(job_id)
    if batch_id:
        job_clauses.append("ingest_batch_id = %s::uuid")
        job_params.append(batch_id)
    if authority_id:
        job_clauses.append("authority_id = %s")
        job_params.append(authority_id)
    if plan_cycle_val:
        job_clauses.append("plan_cycle_id = %s::uuid")
        job_params.append(plan_cycle_val)
    job_where = " AND ".join(job_clauses) if job_clauses else "TRUE"

    run_clauses: list[str] = []
    run_params: list[Any] = []
    if scope == "running":
        run_clauses.append("status IN ('running', 'pending')")
    if run_id_val:
        run_clauses.append("id = %s::uuid")
        run_params.append(run_id_val)
    if batch_id:
        run_clauses.append("ingest_batch_id = %s::uuid")
        run_params.append(batch_id)
    if authority_id:
        run_clauses.append("authority_id = %s")
        run_params.append(authority_id)
    if plan_cycle_val:
        run_clauses.append("plan_cycle_id = %s::uuid")
        run_params.append(plan_cycle_val)
    run_where = " AND ".join(run_clauses) if run_clauses else "TRUE"

    step_clauses: list[str] = []
    step_params: list[Any] = []
    if run_id_val:
        step_clauses.append("id = %s::uuid")
        step_params.append(run_id_val)
    if batch_id:
        step_clauses.append("ingest_batch_id = %s::uuid")
        step_params.append(batch_id)
    if authority_id:
        step_clauses.append("authority_id = %s")
        step_params.append(authority_id)
    if plan_cycle_val:
        step_clauses.append("plan_cycle_id = %s::uuid")
        step_params.append(plan_cycle_val)
    step_where = " AND ".join(step_clauses) if step_clauses else "TRUE"

    batch_clauses: list[str] = []
    batch_params: list[Any] = []
    if scope == "running":
        batch_clauses.append("status IN ('running', 'pending')")
    if batch_id:
        batch_clauses.append("id = %s::uuid")
        batch_params.append(batch_id)
    if authority_id:
        batch_clauses.append("authority_id = %s")
        batch_params.append(authority_id)
    if plan_cycle_val:
        batch_clauses.append("plan_cycle_id = %s::uuid")
        batch_params.append(plan_cycle_val)
    batch_where = " AND ".join(batch_clauses) if batch_clauses else "TRUE"

    jobs_updated = _db_fetch_all(
        f"""
        UPDATE ingest_jobs
        SET status = 'error',
            error_text = COALESCE(error_text, %s),
            completed_at = NOW()
        WHERE {job_where}
        RETURNING id
        """,
        tuple([note_text] + job_params),
    )

    runs_updated = _db_fetch_all(
        f"""
        UPDATE ingest_runs
        SET status = 'error',
            error_text = COALESCE(error_text, %s),
            ended_at = NOW()
        WHERE {run_where}
        RETURNING id
        """,
        tuple([note_text] + run_params),
    )

    steps_updated = _db_fetch_all(
        f"""
        UPDATE ingest_run_steps
        SET status = 'error',
            error_text = COALESCE(error_text, %s),
            ended_at = NOW()
        WHERE run_id IN (
            SELECT id FROM ingest_runs WHERE {step_where}
        )
        RETURNING id
        """,
        tuple([note_text] + step_params),
    )

    batches_updated = _db_fetch_all(
        f"""
        UPDATE ingest_batches
        SET status = 'error',
            notes = COALESCE(notes, %s),
            completed_at = NOW()
        WHERE {batch_where}
        RETURNING id
        """,
        tuple([note_text] + batch_params),
    )

    return JSONResponse(
        content=jsonable_encoder(
            {
                "jobs_updated": len(jobs_updated),
                "runs_updated": len(runs_updated),
                "steps_updated": len(steps_updated),
                "batches_updated": len(batches_updated),
            }
        )
    )


def requeue_ingest_job(ingest_job_id: str, note: str | None = None) -> JSONResponse:
    job_id = _validate_uuid_or_400(ingest_job_id, field_name="ingest_job_id")
    job = _db_fetch_one(
        "SELECT id, ingest_batch_id FROM ingest_jobs WHERE id = %s::uuid",
        (job_id,),
    )
    if not job:
        raise HTTPException(status_code=404, detail="Ingest job not found")
    _db_fetch_all(
        """
        UPDATE ingest_jobs
        SET status = 'pending',
            started_at = NULL,
            completed_at = NULL,
            error_text = NULL,
            outputs_jsonb = '{}'::jsonb
        WHERE id = %s::uuid
        RETURNING id
        """,
        (job_id,),
    )
    if job.get("ingest_batch_id"):
        _db_execute(
            """
            UPDATE ingest_batches
            SET status = 'running',
                completed_at = NULL,
                notes = COALESCE(notes, %s)
            WHERE id = %s::uuid
            """,
            (note or "requeued via debug", job.get("ingest_batch_id")),
        )
    from ..services.ingest import _enqueue_ingest_job  # noqa: PLC0415

    enqueued, error = _enqueue_ingest_job(job_id)
    if not enqueued:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue ingest job: {error}")
    return JSONResponse(content=jsonable_encoder({"ingest_job_id": job_id, "enqueued": True}))


def run_graph_ingest_job(ingest_job_id: str, note: str | None = None) -> JSONResponse:
    job_id = _validate_uuid_or_400(ingest_job_id, field_name="ingest_job_id")
    job = _db_fetch_one(
        "SELECT id FROM ingest_jobs WHERE id = %s::uuid",
        (job_id,),
    )
    if not job:
        raise HTTPException(status_code=404, detail="Ingest job not found")
    try:
        from ..ingestion.tasks import celery_app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"celery_import_failed:{exc}") from exc
    try:
        celery_app.send_task("tpa_api.ingestion.tasks.run_graph_job", args=[job_id])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"celery_enqueue_failed:{exc}") from exc
    if note:
        _db_execute(
            """
            UPDATE ingest_jobs
            SET outputs_jsonb = outputs_jsonb || %s::jsonb
            WHERE id = %s::uuid
            """,
            (json.dumps({"debug_note": note}, ensure_ascii=False), job_id),
        )
    return JSONResponse(content=jsonable_encoder({"ingest_job_id": job_id, "enqueued": True, "mode": "graph"}))
