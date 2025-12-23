from __future__ import annotations

import json
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..cache import cache_get_json, cache_key, cache_set_json
from ..db import _db_fetch_one
from ..prompting import _llm_structured_sync
from ..time_utils import _utc_now_iso


class ScenarioInspectorRequest(BaseModel):
    plan_project_id: str
    culp_stage_id: str | None = None
    force_refresh: bool = False


def _fetch_scalar(sql: str, params: tuple[Any, ...]) -> int:
    row = _db_fetch_one(sql, params)
    if not row:
        return 0
    value = next(iter(row.values()))
    try:
        return int(value or 0)
    except Exception:  # noqa: BLE001
        return 0


def run_scenario_inspector(body: ScenarioInspectorRequest) -> JSONResponse:
    cache_id = cache_key("scenario_inspector", body.plan_project_id, body.culp_stage_id or "stage")
    if not body.force_refresh:
        cached = cache_get_json(cache_id)
        if cached:
            return JSONResponse(content=jsonable_encoder({"report": cached, "cached": True}))

    plan_project = _db_fetch_one(
        """
        SELECT id, authority_id, title, status, current_stage_id, metadata_jsonb
        FROM plan_projects
        WHERE id = %s::uuid
        """,
        (body.plan_project_id,),
    )
    if not plan_project:
        return JSONResponse(status_code=404, content=jsonable_encoder({"detail": "Plan project not found"}))

    metadata = plan_project.get("metadata_jsonb") if isinstance(plan_project.get("metadata_jsonb"), dict) else {}

    counts = {
        "evidence_items": _fetch_scalar("SELECT COUNT(*) FROM evidence_items WHERE plan_project_id = %s::uuid", (body.plan_project_id,)),
        "evidence_gaps": _fetch_scalar("SELECT COUNT(*) FROM evidence_gaps WHERE plan_project_id = %s::uuid", (body.plan_project_id,)),
        "consultations": _fetch_scalar("SELECT COUNT(*) FROM consultations WHERE plan_project_id = %s::uuid", (body.plan_project_id,)),
        "consultation_summaries": _fetch_scalar(
            """
            SELECT COUNT(*)
            FROM consultation_summaries cs
            JOIN consultations c ON c.id = cs.consultation_id
            WHERE c.plan_project_id = %s::uuid
            """,
            (body.plan_project_id,),
        ),
        "sites_confirmed": _fetch_scalar("SELECT COUNT(*) FROM sites WHERE metadata->>'plan_project_id' = %s", (body.plan_project_id,)),
        "sites_draft": _fetch_scalar("SELECT COUNT(*) FROM site_drafts WHERE plan_project_id = %s::uuid", (body.plan_project_id,)),
        "site_assessments": _fetch_scalar("SELECT COUNT(*) FROM site_assessments WHERE plan_project_id = %s::uuid", (body.plan_project_id,)),
        "allocation_decisions": _fetch_scalar("SELECT COUNT(*) FROM allocation_decisions WHERE plan_project_id = %s::uuid", (body.plan_project_id,)),
        "visual_assets": _fetch_scalar(
            """
            SELECT COUNT(*)
            FROM visual_assets va
            LEFT JOIN documents d ON d.id = va.document_id
            WHERE (va.metadata->>'plan_project_id' = %s)
               OR (d.authority_id = %s AND (d.plan_cycle_id IS NULL OR d.plan_cycle_id::text = %s))
            """,
            (body.plan_project_id, plan_project["authority_id"], metadata.get("plan_cycle_id", "")),
        ),
    }

    artefacts = _db_fetch_one(
        """
        SELECT jsonb_object_agg(status, count) AS counts
        FROM (
          SELECT status, COUNT(*) AS count
          FROM culp_artefacts
          WHERE plan_project_id = %s::uuid
          GROUP BY status
        ) s
        """,
        (body.plan_project_id,),
    )

    payload = {
        "plan_project": {
            "plan_project_id": str(plan_project["id"]),
            "authority_id": plan_project["authority_id"],
            "title": plan_project["title"],
            "status": plan_project["status"],
            "current_stage_id": plan_project.get("current_stage_id"),
            "culp_stage_id": body.culp_stage_id or plan_project.get("current_stage_id"),
        },
        "counts": counts,
        "artefact_status_counts": artefacts.get("counts") if artefacts and isinstance(artefacts.get("counts"), dict) else {},
        "timestamp": _utc_now_iso(),
    }

    system = (
        "You are an AI planning inspector assessing whether the evidence base and workflow context are ready for scenario work.\n"
        "Return ONLY JSON.\n"
        "Output shape:\n"
        "{\n"
        "  \"decision\": \"ready\" | \"needs_more\" | \"blocked\",\n"
        "  \"summary\": string,\n"
        "  \"scorecard\": [{\"dimension\": string, \"rating\": \"strong\"|\"mixed\"|\"weak\"|\"missing\", \"notes\": string}],\n"
        "  \"blockers\": [{\"title\": string, \"detail\": string}],\n"
        "  \"suggestions\": [{\"title\": string, \"detail\": string}],\n"
        "  \"cache_tier_hint\": \"fast\"|\"normal\"|\"slow\"\n"
        "}\n"
    )

    report, tool_run_id, errors = _llm_structured_sync(
        prompt_id="scenario_inspector_v1",
        prompt_version=1,
        prompt_name="Scenario Inspector",
        purpose="Assess readiness for scenario generation and provide planner-facing report cards.",
        system_template=system,
        user_payload=payload,
        output_schema_ref="schemas/InspectorReport.schema.json",
    )

    if not report:
        report = {
            "decision": "needs_more",
            "summary": "Inspector could not run (LLM unavailable).",
            "scorecard": [{"dimension": "LLM", "rating": "missing", "notes": "; ".join(errors) if errors else "LLM unavailable."}],
            "blockers": [{"title": "LLM unavailable", "detail": "Configure TPA_LLM_BASE_URL to enable inspector reports."}],
            "suggestions": [],
            "cache_tier_hint": "slow",
        }

    cache_set_json(cache_id, report, ttl_seconds=300)

    return JSONResponse(
        content=jsonable_encoder(
            {
                "report": report,
                "tool_run_id": tool_run_id,
                "cached": False,
            }
        )
    )
