from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import _db_execute, _db_execute_returning, _db_fetch_all, _db_fetch_one
from ..time_utils import _utc_now


class SiteCategoryCreate(BaseModel):
    plan_project_id: str
    name: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SiteCreate(BaseModel):
    plan_project_id: str | None = None
    geometry_wkt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SiteAssessmentCreate(BaseModel):
    plan_project_id: str
    site_id: str
    stage: str
    suitability: str | None = None
    availability: str | None = None
    achievability: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SiteScoreCreate(BaseModel):
    site_assessment_id: str
    dimension: str
    rag: str
    rationale: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class MitigationCreate(BaseModel):
    site_assessment_id: str
    description: str
    status: str = Field(default="proposed")
    evidence_refs: list[str] = Field(default_factory=list)


class AllocationDecisionCreate(BaseModel):
    plan_project_id: str
    site_id: str
    decision_status: str
    reason: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class DecisionLogCreate(BaseModel):
    allocation_decision_id: str
    stage: str
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Stage4SummaryRowCreate(BaseModel):
    plan_project_id: str
    site_id: str
    category: str
    capacity: int | None = None
    phasing: str | None = None
    rag_overall: str | None = None
    rag_suitability: str | None = None
    rag_availability: str | None = None
    rag_achievability: str | None = None
    justification: str | None = None
    deliverable_status: str | None = None


def create_site_category(body: SiteCategoryCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO site_categories (
          id, plan_project_id, name, description, metadata_jsonb, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s, %s)
        RETURNING id, plan_project_id, name, description, metadata_jsonb, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            body.name,
            body.description,
            json.dumps(body.metadata, ensure_ascii=False),
            now,
            now,
        ),
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "site_category_id": str(row["id"]),
                "plan_project_id": str(row["plan_project_id"]),
                "name": row["name"],
                "description": row.get("description"),
                "metadata": row.get("metadata_jsonb") or {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    )


def create_site(body: SiteCreate) -> JSONResponse:
    metadata = dict(body.metadata)
    if body.plan_project_id and "plan_project_id" not in metadata:
        metadata["plan_project_id"] = body.plan_project_id
    if body.geometry_wkt:
        row = _db_execute_returning(
            """
            INSERT INTO sites (id, geometry_polygon, metadata)
            VALUES (%s, ST_GeomFromText(%s, 4326), %s::jsonb)
            RETURNING id, geometry_polygon, metadata
            """,
        (
            str(uuid4()),
            body.geometry_wkt,
            json.dumps(metadata, ensure_ascii=False),
        ),
    )
    else:
        row = _db_execute_returning(
            """
            INSERT INTO sites (id, geometry_polygon, metadata)
            VALUES (%s, NULL, %s::jsonb)
            RETURNING id, geometry_polygon, metadata
            """,
            (
                str(uuid4()),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "site_id": str(row["id"]),
                "geometry": row.get("geometry_polygon"),
                "metadata": row.get("metadata") or {},
            }
        )
    )


def list_sites(limit: int = 50) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, geometry_polygon, metadata
        FROM sites
        ORDER BY id DESC
        LIMIT %s
        """,
        (limit,),
    )
    items = [
        {
            "site_id": str(r["id"]),
            "geometry": r.get("geometry_polygon"),
            "metadata": r.get("metadata") or {},
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"sites": items}))


def list_site_categories(plan_project_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, plan_project_id, name, description, metadata_jsonb, created_at, updated_at
        FROM site_categories
        WHERE plan_project_id = %s::uuid
        ORDER BY name
        """,
        (plan_project_id,),
    )
    items = [
        {
            "site_category_id": str(r["id"]),
            "plan_project_id": str(r["plan_project_id"]),
            "name": r["name"],
            "description": r.get("description"),
            "metadata": r.get("metadata_jsonb") or {},
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"site_categories": items}))


def create_site_assessment(body: SiteAssessmentCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO site_assessments (
          id, site_id, plan_project_id, stage, suitability, availability, achievability, notes,
          metadata_jsonb, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
        RETURNING id, site_id, plan_project_id, stage, suitability, availability, achievability, notes,
                  metadata_jsonb, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.site_id,
            body.plan_project_id,
            body.stage,
            body.suitability,
            body.availability,
            body.achievability,
            body.notes,
            json.dumps(body.metadata, ensure_ascii=False),
            now,
            now,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_site_assessment(row)))


def list_site_assessments(plan_project_id: str, stage: str | None = None) -> JSONResponse:
    params: list[Any] = [plan_project_id]
    clause = ""
    if stage:
        clause = "AND stage = %s"
        params.append(stage)
    rows = _db_fetch_all(
        f"""
        SELECT id, site_id, plan_project_id, stage, suitability, availability, achievability, notes,
               metadata_jsonb, created_at, updated_at
        FROM site_assessments
        WHERE plan_project_id = %s::uuid {clause}
        ORDER BY updated_at DESC
        """,
        tuple(params),
    )
    items = [_row_to_site_assessment(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"site_assessments": items}))


def create_site_score(body: SiteScoreCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO site_scores (
          id, site_assessment_id, dimension, rag, rationale, evidence_refs_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s, %s::jsonb, %s)
        RETURNING id, site_assessment_id, dimension, rag, rationale, evidence_refs_jsonb, created_at
        """,
        (
            str(uuid4()),
            body.site_assessment_id,
            body.dimension,
            body.rag,
            body.rationale,
            json.dumps(body.evidence_refs, ensure_ascii=False),
            now,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_site_score(row)))


def list_site_scores(site_assessment_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, site_assessment_id, dimension, rag, rationale, evidence_refs_jsonb, created_at
        FROM site_scores
        WHERE site_assessment_id = %s::uuid
        ORDER BY created_at DESC
        """,
        (site_assessment_id,),
    )
    items = [_row_to_site_score(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"site_scores": items}))


def create_mitigation(body: MitigationCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO mitigations (
          id, site_assessment_id, description, status, evidence_refs_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s)
        RETURNING id, site_assessment_id, description, status, evidence_refs_jsonb, created_at
        """,
        (
            str(uuid4()),
            body.site_assessment_id,
            body.description,
            body.status,
            json.dumps(body.evidence_refs, ensure_ascii=False),
            now,
        ),
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "mitigation_id": str(row["id"]),
                "site_assessment_id": str(row["site_assessment_id"]),
                "description": row["description"],
                "status": row["status"],
                "evidence_refs": row.get("evidence_refs_jsonb") or [],
                "created_at": row["created_at"],
            }
        )
    )


def list_mitigations(site_assessment_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, site_assessment_id, description, status, evidence_refs_jsonb, created_at
        FROM mitigations
        WHERE site_assessment_id = %s::uuid
        ORDER BY created_at DESC
        """,
        (site_assessment_id,),
    )
    items = [
        {
            "mitigation_id": str(r["id"]),
            "site_assessment_id": str(r["site_assessment_id"]),
            "description": r["description"],
            "status": r["status"],
            "evidence_refs": r.get("evidence_refs_jsonb") or [],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"mitigations": items}))


def create_allocation_decision(body: AllocationDecisionCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO allocation_decisions (
          id, plan_project_id, site_id, decision_status, reason, evidence_refs_jsonb, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s, %s)
        RETURNING id, plan_project_id, site_id, decision_status, reason, evidence_refs_jsonb, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            body.site_id,
            body.decision_status,
            body.reason,
            json.dumps(body.evidence_refs, ensure_ascii=False),
            now,
            now,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_allocation(row)))


def list_allocation_decisions(plan_project_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, plan_project_id, site_id, decision_status, reason, evidence_refs_jsonb, created_at, updated_at
        FROM allocation_decisions
        WHERE plan_project_id = %s::uuid
        ORDER BY updated_at DESC
        """,
        (plan_project_id,),
    )
    items = [_row_to_allocation(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"allocation_decisions": items}))


def create_decision_log(body: DecisionLogCreate) -> JSONResponse:
    row = _db_execute_returning(
        """
        INSERT INTO decision_logs (
          id, allocation_decision_id, stage, changed_at, summary, metadata_jsonb
        )
        VALUES (%s, %s::uuid, %s, %s, %s, %s::jsonb)
        RETURNING id, allocation_decision_id, stage, changed_at, summary, metadata_jsonb
        """,
        (
            str(uuid4()),
            body.allocation_decision_id,
            body.stage,
            _utc_now(),
            body.summary,
            json.dumps(body.metadata, ensure_ascii=False),
        ),
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "decision_log_id": str(row["id"]),
                "allocation_decision_id": str(row["allocation_decision_id"]),
                "stage": row["stage"],
                "changed_at": row["changed_at"],
                "summary": row["summary"],
                "metadata": row.get("metadata_jsonb") or {},
            }
        )
    )


def list_decision_logs(allocation_decision_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, allocation_decision_id, stage, changed_at, summary, metadata_jsonb
        FROM decision_logs
        WHERE allocation_decision_id = %s::uuid
        ORDER BY changed_at DESC
        """,
        (allocation_decision_id,),
    )
    items = [
        {
            "decision_log_id": str(r["id"]),
            "allocation_decision_id": str(r["allocation_decision_id"]),
            "stage": r["stage"],
            "changed_at": r["changed_at"],
            "summary": r["summary"],
            "metadata": r.get("metadata_jsonb") or {},
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"decision_logs": items}))


def create_stage4_summary_row(body: Stage4SummaryRowCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO stage4_summary_rows (
          id, plan_project_id, site_id, category, capacity, phasing, rag_overall, rag_suitability,
          rag_availability, rag_achievability, justification, deliverable_status, created_at, updated_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, plan_project_id, site_id, category, capacity, phasing, rag_overall, rag_suitability,
                  rag_availability, rag_achievability, justification, deliverable_status, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            body.site_id,
            body.category,
            body.capacity,
            body.phasing,
            body.rag_overall,
            body.rag_suitability,
            body.rag_availability,
            body.rag_achievability,
            body.justification,
            body.deliverable_status,
            now,
            now,
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_stage4(row)))


def list_stage4_summary_rows(plan_project_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, plan_project_id, site_id, category, capacity, phasing, rag_overall, rag_suitability,
               rag_availability, rag_achievability, justification, deliverable_status, created_at, updated_at
        FROM stage4_summary_rows
        WHERE plan_project_id = %s::uuid
        ORDER BY updated_at DESC
        """,
        (plan_project_id,),
    )
    items = [_row_to_stage4(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"stage4_summary_rows": items}))


def _row_to_site_assessment(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "site_assessment_id": str(row["id"]),
        "site_id": str(row["site_id"]),
        "plan_project_id": str(row["plan_project_id"]),
        "stage": row["stage"],
        "suitability": row.get("suitability"),
        "availability": row.get("availability"),
        "achievability": row.get("achievability"),
        "notes": row.get("notes"),
        "metadata": row.get("metadata_jsonb") or {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_site_score(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "site_score_id": str(row["id"]),
        "site_assessment_id": str(row["site_assessment_id"]),
        "dimension": row["dimension"],
        "rag": row["rag"],
        "rationale": row.get("rationale"),
        "evidence_refs": row.get("evidence_refs_jsonb") or [],
        "created_at": row["created_at"],
    }


def _row_to_allocation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "allocation_decision_id": str(row["id"]),
        "plan_project_id": str(row["plan_project_id"]),
        "site_id": str(row["site_id"]),
        "decision_status": row["decision_status"],
        "reason": row.get("reason"),
        "evidence_refs": row.get("evidence_refs_jsonb") or [],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_stage4(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage4_row_id": str(row["id"]),
        "plan_project_id": str(row["plan_project_id"]),
        "site_id": str(row["site_id"]),
        "category": row["category"],
        "capacity": row.get("capacity"),
        "phasing": row.get("phasing"),
        "rag_overall": row.get("rag_overall"),
        "rag_suitability": row.get("rag_suitability"),
        "rag_availability": row.get("rag_availability"),
        "rag_achievability": row.get("rag_achievability"),
        "justification": row.get("justification"),
        "deliverable_status": row.get("deliverable_status"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
