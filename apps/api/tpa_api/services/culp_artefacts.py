from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..db import _db_execute, _db_fetch_all, _db_fetch_one
from ..spec_io import _read_yaml, _spec_root
from ..time_utils import _utc_now


def _load_process_model() -> dict[str, Any]:
    root = _spec_root()
    return _read_yaml(root / "culp" / "PROCESS_MODEL.yaml") or {}


def _load_artefact_registry() -> dict[str, Any]:
    root = _spec_root()
    return _read_yaml(root / "culp" / "ARTEFACT_REGISTRY.yaml") or {}


def ensure_culp_artefacts(plan_project_id: str, process_model_id: str | None = None) -> None:
    process_model = _load_process_model()
    if process_model_id and process_model.get("process_id") != process_model_id:
        raise HTTPException(status_code=400, detail="Process model ID mismatch for CULP artefact bootstrap")
    registry = _load_artefact_registry()
    registry_keys = {a.get("artefact_key") for a in registry.get("artefacts", []) if isinstance(a, dict)}
    stages = process_model.get("stages") if isinstance(process_model.get("stages"), list) else []
    now = _utc_now()
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage_id = stage.get("id")
        required = stage.get("required_artefacts", [])
        if not stage_id or not isinstance(required, list):
            continue
        for artefact_key in required:
            if artefact_key not in registry_keys:
                continue
            existing = _db_fetch_one(
                """
                SELECT id FROM culp_artefacts
                WHERE plan_project_id = %s::uuid AND culp_stage_id = %s AND artefact_key = %s
                """,
                (plan_project_id, stage_id, artefact_key),
            )
            if existing:
                continue
            _db_execute(
                """
                INSERT INTO culp_artefacts (
                  id, plan_project_id, culp_stage_id, artefact_key, status,
                  evidence_refs_jsonb, tool_run_ids_jsonb, created_at, updated_at
                )
                VALUES (%s, %s::uuid, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                """,
                (
                    str(uuid4()),
                    plan_project_id,
                    stage_id,
                    artefact_key,
                    "missing",
                    json.dumps([], ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    now,
                    now,
                ),
            )


def list_culp_artefacts(plan_project_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, plan_project_id, culp_stage_id, artefact_key, status, authored_artefact_id,
               artifact_path, evidence_refs_jsonb, produced_by_run_id, tool_run_ids_jsonb,
               created_at, updated_at, notes
        FROM culp_artefacts
        WHERE plan_project_id = %s::uuid
        ORDER BY culp_stage_id, artefact_key
        """,
        (plan_project_id,),
    )
    items = [
        {
            "culp_artefact_id": str(r["id"]),
            "plan_project_id": str(r["plan_project_id"]),
            "culp_stage_id": r["culp_stage_id"],
            "artefact_key": r["artefact_key"],
            "status": r["status"],
            "authored_artefact_id": str(r["authored_artefact_id"]) if r.get("authored_artefact_id") else None,
            "artifact_path": r.get("artifact_path"),
            "evidence_refs": r.get("evidence_refs_jsonb") or [],
            "produced_by_run_id": str(r["produced_by_run_id"]) if r.get("produced_by_run_id") else None,
            "tool_run_ids": r.get("tool_run_ids_jsonb") or [],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "notes": r.get("notes"),
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"culp_artefacts": items}))


def update_culp_artefact(culp_artefact_id: str, updates: dict[str, Any]) -> JSONResponse:
    row = _db_fetch_one("SELECT id FROM culp_artefacts WHERE id = %s::uuid", (culp_artefact_id,))
    if not row:
        raise HTTPException(status_code=404, detail="CULP artefact not found")
    allowed = {"status", "authored_artefact_id", "artifact_path", "evidence_refs", "notes"}
    set_clauses = []
    params: list[Any] = []
    if "status" in updates:
        set_clauses.append("status = %s")
        params.append(updates.get("status"))
    if "authored_artefact_id" in updates:
        set_clauses.append("authored_artefact_id = %s::uuid")
        params.append(updates.get("authored_artefact_id"))
    if "artifact_path" in updates:
        set_clauses.append("artifact_path = %s")
        params.append(updates.get("artifact_path"))
    if "evidence_refs" in updates:
        set_clauses.append("evidence_refs_jsonb = %s::jsonb")
        params.append(json.dumps(updates.get("evidence_refs") or [], ensure_ascii=False))
    if "notes" in updates:
        set_clauses.append("notes = %s")
        params.append(updates.get("notes"))
    unknown = [k for k in updates.keys() if k not in allowed]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown fields: {', '.join(unknown)}")
    if not set_clauses:
        raise HTTPException(status_code=400, detail="No updates provided")
    now = _utc_now()
    params.append(now)
    params.append(culp_artefact_id)
    _db_execute(
        f"UPDATE culp_artefacts SET {', '.join(set_clauses)}, updated_at = %s WHERE id = %s::uuid",
        tuple(params),
    )
    updated = _db_fetch_one(
        """
        SELECT id, plan_project_id, culp_stage_id, artefact_key, status, authored_artefact_id,
               artifact_path, evidence_refs_jsonb, produced_by_run_id, tool_run_ids_jsonb,
               created_at, updated_at, notes
        FROM culp_artefacts
        WHERE id = %s::uuid
        """,
        (culp_artefact_id,),
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "culp_artefact_id": str(updated["id"]),
                "plan_project_id": str(updated["plan_project_id"]),
                "culp_stage_id": updated["culp_stage_id"],
                "artefact_key": updated["artefact_key"],
                "status": updated["status"],
                "authored_artefact_id": (
                    str(updated["authored_artefact_id"]) if updated.get("authored_artefact_id") else None
                ),
                "artifact_path": updated.get("artifact_path"),
                "evidence_refs": updated.get("evidence_refs_jsonb") or [],
                "produced_by_run_id": (
                    str(updated["produced_by_run_id"]) if updated.get("produced_by_run_id") else None
                ),
                "tool_run_ids": updated.get("tool_run_ids_jsonb") or [],
                "created_at": updated["created_at"],
                "updated_at": updated["updated_at"],
                "notes": updated.get("notes"),
            }
        )
    )
