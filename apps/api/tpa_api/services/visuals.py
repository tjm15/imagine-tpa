from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..blob_store import read_blob_bytes, to_data_url
from ..db import _db_fetch_all, _db_fetch_one


def list_visual_assets(
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    document_id: str | None = None,
    plan_project_id: str | None = None,
    limit: int = 80,
) -> JSONResponse:
    limit = max(1, min(int(limit), 200))
    clauses = []
    params: list[Any] = []
    if document_id:
        clauses.append("va.document_id = %s::uuid")
        params.append(document_id)
    if authority_id:
        clauses.append("d.authority_id = %s")
        params.append(authority_id)
    if plan_cycle_id:
        clauses.append("d.plan_cycle_id = %s::uuid")
        params.append(plan_cycle_id)
    if plan_project_id:
        clauses.append("va.metadata->>'plan_project_id' = %s")
        params.append(plan_project_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = _db_fetch_all(
        f"""
        SELECT va.id, va.document_id, va.page_number, va.asset_type, va.blob_path, va.metadata, va.created_at, va.updated_at,
               d.authority_id, d.plan_cycle_id
        FROM visual_assets va
        LEFT JOIN documents d ON d.id = va.document_id
        {where}
        ORDER BY va.page_number NULLS LAST, va.id DESC
        LIMIT %s
        """,
        tuple(params + [limit]),
    )
    items = [
        {
            "visual_asset_id": str(r["id"]),
            "document_id": str(r["document_id"]) if r.get("document_id") else None,
            "page_number": r.get("page_number"),
            "asset_type": r.get("asset_type"),
            "blob_path": r.get("blob_path"),
            "metadata": r.get("metadata") or {},
            "authority_id": r.get("authority_id"),
            "plan_cycle_id": str(r["plan_cycle_id"]) if r.get("plan_cycle_id") else None,
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"visual_assets": items}))


def list_visual_features(visual_asset_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, visual_asset_id, feature_type, geometry_jsonb, confidence, evidence_ref_id, tool_run_id, metadata_jsonb
        FROM visual_features
        WHERE visual_asset_id = %s::uuid
        ORDER BY id DESC
        """,
        (visual_asset_id,),
    )
    items = [
        {
            "visual_feature_id": str(r["id"]),
            "visual_asset_id": str(r["visual_asset_id"]),
            "feature_type": r.get("feature_type"),
            "geometry": r.get("geometry_jsonb"),
            "confidence": r.get("confidence"),
            "evidence_ref_id": str(r["evidence_ref_id"]) if r.get("evidence_ref_id") else None,
            "tool_run_id": str(r["tool_run_id"]) if r.get("tool_run_id") else None,
            "metadata": r.get("metadata_jsonb") or {},
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"visual_features": items}))


def get_visual_asset_blob(visual_asset_id: str) -> JSONResponse:
    row = _db_fetch_one("SELECT blob_path FROM visual_assets WHERE id = %s::uuid", (visual_asset_id,))
    if not row or not row.get("blob_path"):
        raise HTTPException(status_code=404, detail="Visual asset not found")
    data, content_type, err = read_blob_bytes(str(row["blob_path"]))
    if err or not data:
        raise HTTPException(status_code=404, detail=f"Visual asset blob not available: {err}")
    return JSONResponse(content=jsonable_encoder({"data_url": to_data_url(data, content_type or "image/png")}))
