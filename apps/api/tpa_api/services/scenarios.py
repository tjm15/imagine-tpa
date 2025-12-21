from __future__ import annotations

import json
import os
import threading
from datetime import timedelta
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..audit import _audit_event
from ..cache import cache_get_json, cache_key, cache_set_json
from ..context_assembly import ContextAssemblyDeps, assemble_curated_evidence_set_sync
from ..db import _db_execute, _db_execute_returning, _db_fetch_all, _db_fetch_one
from ..evidence import _ensure_evidence_ref_row
from ..hash_utils import stable_hash
from ..prompting import _llm_structured_sync
from ..retrieval import _retrieve_chunks_hybrid_sync, _retrieve_policy_clauses_hybrid_sync
from ..spec_io import _read_yaml, _spec_root
from ..time_utils import _utc_now, _utc_now_iso
from ..tool_requests import persist_tool_requests_for_move, _run_render_simple_chart_sync


_SCENARIO_CACHE_TTL_SECONDS = int(os.environ.get("TPA_SCENARIO_CACHE_TTL_SECONDS", "900"))
_SCENARIO_CACHE_SOFT_TTL_SECONDS = int(os.environ.get("TPA_SCENARIO_CACHE_SOFT_TTL_SECONDS", "120"))


def _iso(value: Any | None) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _fetch_max_timestamp(sql: str, params: tuple[Any, ...]) -> str | None:
    row = _db_fetch_one(sql, params)
    if not row:
        return None
    value = next(iter(row.values())) if row else None
    return _iso(value)


def _scenario_dependency_snapshot(tab: dict[str, Any]) -> dict[str, Any]:
    scenario_state = tab.get("state_vector_jsonb") if isinstance(tab.get("state_vector_jsonb"), dict) else {}
    plan_project_id = tab.get("plan_project_id")
    authority_id = tab.get("authority_id")
    plan_cycle_id = tab.get("plan_cycle_id")

    site_updates = _fetch_max_timestamp(
        "SELECT MAX(updated_at) FROM site_assessments WHERE plan_project_id = %s::uuid",
        (plan_project_id,),
    )
    allocation_updates = _fetch_max_timestamp(
        "SELECT MAX(updated_at) FROM allocation_decisions WHERE plan_project_id = %s::uuid",
        (plan_project_id,),
    )
    stage4_updates = _fetch_max_timestamp(
        "SELECT MAX(updated_at) FROM stage4_summary_rows WHERE plan_project_id = %s::uuid",
        (plan_project_id,),
    )
    evidence_updates = _fetch_max_timestamp(
        "SELECT MAX(updated_at) FROM evidence_items WHERE plan_project_id = %s::uuid",
        (plan_project_id,),
    )
    gap_updates = _fetch_max_timestamp(
        "SELECT MAX(updated_at) FROM evidence_gaps WHERE plan_project_id = %s::uuid",
        (plan_project_id,),
    )
    trace_updates = _fetch_max_timestamp(
        "SELECT MAX(created_at) FROM trace_links",
        (),
    )
    policy_counts = _db_fetch_one(
        """
        SELECT COUNT(*) AS policy_count
        FROM policy_sections ps
        JOIN documents d ON d.id = ps.document_id
        WHERE (%s IS NULL OR d.authority_id = %s)
          AND (%s IS NULL OR d.plan_cycle_id = %s::uuid)
        """,
        (authority_id, authority_id, plan_cycle_id, plan_cycle_id),
    )
    clause_counts = _db_fetch_one(
        """
        SELECT COUNT(*) AS clause_count
        FROM policy_clauses pc
        JOIN policy_sections ps ON ps.id = pc.policy_section_id
        JOIN documents d ON d.id = ps.document_id
        WHERE (%s IS NULL OR d.authority_id = %s)
          AND (%s IS NULL OR d.plan_cycle_id = %s::uuid)
        """,
        (authority_id, authority_id, plan_cycle_id, plan_cycle_id),
    )
    visual_counts = _db_fetch_one(
        """
        SELECT COUNT(*) AS visual_count
        FROM visual_assets va
        LEFT JOIN documents d ON d.id = va.document_id
        WHERE (%s IS NULL OR d.authority_id = %s OR va.metadata->>'authority_id' = %s)
          AND (%s IS NULL OR d.plan_cycle_id = %s::uuid OR va.metadata->>'plan_cycle_id' = %s)
          AND (%s IS NULL OR va.metadata->>'plan_project_id' = %s)
        """,
        (
            authority_id,
            authority_id,
            authority_id,
            plan_cycle_id,
            plan_cycle_id,
            plan_cycle_id,
            plan_project_id,
            plan_project_id,
        ),
    )
    ingest_updates = _fetch_max_timestamp(
        """
        SELECT MAX(completed_at) FROM ingest_batches
        WHERE (%s IS NULL OR authority_id = %s)
          AND (%s IS NULL OR plan_cycle_id = %s::uuid)
        """,
        (authority_id, authority_id, plan_cycle_id, plan_cycle_id),
    )

    return {
        "scenario_state_hash": stable_hash(scenario_state),
        "scenario_updated_at": _iso(tab.get("scenario_updated_at")),
        "plan_project_updated_at": _iso(tab.get("plan_project_updated_at")),
        "site_updates_at": site_updates,
        "allocation_updates_at": allocation_updates,
        "stage4_updates_at": stage4_updates,
        "evidence_updates_at": evidence_updates,
        "evidence_gap_updates_at": gap_updates,
        "trace_updates_at": trace_updates,
        "policy_clause_count": clause_counts.get("clause_count") if clause_counts else 0,
        "policy_count": policy_counts.get("policy_count") if policy_counts else 0,
        "visual_asset_count": visual_counts.get("visual_count") if visual_counts else 0,
        "ingest_updates_at": ingest_updates,
    }


def _schedule_tab_refresh(tab_id: str) -> None:
    now = _utc_now()
    try:
        _db_execute(
            "UPDATE scenario_framing_tabs SET status = %s, updated_at = %s WHERE id = %s::uuid",
            ("queued", now, tab_id),
        )
    except Exception:  # noqa: BLE001
        pass

    def _runner() -> None:
        try:
            run_scenario_framing_tab(tab_id)
        except Exception:
            return

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()



def list_scenarios(plan_project_id: str | None = None, culp_stage_id: str | None = None, limit: int = 100) -> JSONResponse:
    limit = max(1, min(int(limit), 500))
    where: list[str] = []
    params: list[Any] = []
    if plan_project_id:
        where.append("plan_project_id = %s::uuid")
        params.append(plan_project_id)
    if culp_stage_id:
        where.append("culp_stage_id = %s")
        params.append(culp_stage_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = _db_fetch_all(
        f"""
        SELECT
          id, plan_project_id, culp_stage_id, title, summary,
          state_vector_jsonb, parent_scenario_id, status, created_by, created_at, updated_at
        FROM scenarios
        {where_sql}
        ORDER BY updated_at DESC
        LIMIT %s
        """,
        tuple(params + [limit]),
    )

    items = [
        {
            "scenario_id": str(r["id"]),
            "plan_project_id": str(r["plan_project_id"]),
            "culp_stage_id": r["culp_stage_id"],
            "title": r["title"],
            "summary": r["summary"] or "",
            "state_vector": r["state_vector_jsonb"] or {},
            "parent_scenario_id": str(r["parent_scenario_id"]) if r["parent_scenario_id"] else None,
            "status": r["status"],
            "created_by": r["created_by"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"scenarios": items}))


def list_scenario_sets(
    plan_project_id: str | None = None,
    culp_stage_id: str | None = None,
    limit: int = 25,
) -> JSONResponse:
    limit = max(1, min(int(limit), 200))
    where: list[str] = []
    params: list[Any] = []
    if plan_project_id:
        where.append("plan_project_id = %s::uuid")
        params.append(plan_project_id)
    if culp_stage_id:
        where.append("culp_stage_id = %s")
        params.append(culp_stage_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = _db_fetch_all(
        f"""
        SELECT id, plan_project_id, culp_stage_id, tab_ids_jsonb, selected_tab_id, selected_at
        FROM scenario_sets
        {where_sql}
        ORDER BY selected_at DESC NULLS LAST
        LIMIT %s
        """,
        tuple(params + [limit]),
    )
    items = [
        {
            "scenario_set_id": str(r["id"]),
            "plan_project_id": str(r["plan_project_id"]),
            "culp_stage_id": r["culp_stage_id"],
            "tab_count": len(r["tab_ids_jsonb"] or []),
            "selected_tab_id": str(r["selected_tab_id"]) if r["selected_tab_id"] else None,
            "selected_at": r["selected_at"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"scenario_sets": items}))


class ScenarioCreate(BaseModel):
    plan_project_id: str
    culp_stage_id: str
    title: str
    summary: str | None = None
    state_vector: dict[str, Any] = Field(default_factory=dict)
    parent_scenario_id: str | None = None
    status: str = Field(default="draft")
    created_by: str = Field(default="user")


def create_scenario(body: ScenarioCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO scenarios (
          id, plan_project_id, culp_stage_id, title, summary, state_vector_jsonb, parent_scenario_id,
          status, created_by, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
        RETURNING id, plan_project_id, culp_stage_id, title, summary, state_vector_jsonb, parent_scenario_id, status, created_by, created_at
        """,
        (
            str(uuid4()),
            body.plan_project_id,
            body.culp_stage_id,
            body.title,
            body.summary,
            json.dumps(body.state_vector, ensure_ascii=False),
            body.parent_scenario_id,
            body.status,
            body.created_by,
            now,
            now,
        ),
    )
    _audit_event(
        event_type="scenario_created",
        plan_project_id=body.plan_project_id,
        culp_stage_id=body.culp_stage_id,
        scenario_id=str(row["id"]),
        payload={"title": body.title},
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "scenario_id": str(row["id"]),
                "plan_project_id": str(row["plan_project_id"]),
                "culp_stage_id": row["culp_stage_id"],
                "title": row["title"],
                "summary": row["summary"] or "",
                "state_vector": row["state_vector_jsonb"] or {},
                "parent_scenario_id": row["parent_scenario_id"],
                "status": row["status"],
                "created_by": row["created_by"],
                "created_at": row["created_at"],
                "assumptions": [],
            }
        )
    )


class ScenarioSetCreate(BaseModel):
    plan_project_id: str
    culp_stage_id: str
    scenario_ids: list[str]
    political_framing_ids: list[str]


class ScenarioSetAutoCreate(BaseModel):
    plan_project_id: str
    culp_stage_id: str
    scenario_count: int = Field(default=2, ge=1, le=4)
    political_framing_ids: list[str] | None = None
    prompt: str | None = None


def create_scenario_set(body: ScenarioSetCreate) -> JSONResponse:
    if not body.scenario_ids:
        raise HTTPException(status_code=400, detail="scenario_ids must not be empty")
    if not body.political_framing_ids:
        raise HTTPException(status_code=400, detail="political_framing_ids must not be empty")

    now = _utc_now()
    scenario_set_id = str(uuid4())
    tab_ids: list[str] = []

    _db_execute(
        """
        INSERT INTO scenario_sets (
          id, plan_project_id, culp_stage_id, political_framing_ids_jsonb, scenario_ids_jsonb, tab_ids_jsonb
        )
        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
        """,
        (
            scenario_set_id,
            body.plan_project_id,
            body.culp_stage_id,
            json.dumps(body.political_framing_ids, ensure_ascii=False),
            json.dumps(body.scenario_ids, ensure_ascii=False),
            "[]",
        ),
    )

    for scenario_id in body.scenario_ids:
        for framing_id in body.political_framing_ids:
            tab_id = str(uuid4())
            tab_ids.append(tab_id)
            _db_execute(
                """
                INSERT INTO scenario_framing_tabs (
                  id, scenario_set_id, scenario_id, political_framing_id, framing_id, run_id, status,
                  trajectory_id, judgement_sheet_ref, updated_at
                )
                VALUES (%s, %s, %s, %s, NULL, NULL, %s, NULL, NULL, %s)
                """,
                (tab_id, scenario_set_id, scenario_id, framing_id, "queued", now),
            )

    _db_execute(
        "UPDATE scenario_sets SET tab_ids_jsonb = %s::jsonb WHERE id = %s",
        (json.dumps(tab_ids, ensure_ascii=False), scenario_set_id),
    )

    _audit_event(
        event_type="scenario_set_created",
        plan_project_id=body.plan_project_id,
        culp_stage_id=body.culp_stage_id,
        payload={"scenario_set_id": scenario_set_id, "tab_count": len(tab_ids)},
    )

    return get_scenario_set(scenario_set_id)


def create_scenario_set_auto(body: ScenarioSetAutoCreate) -> JSONResponse:
    plan_project = _db_fetch_one(
        """
        SELECT id, authority_id, title, status, current_stage_id, metadata_jsonb
        FROM plan_projects
        WHERE id = %s::uuid
        """,
        (body.plan_project_id,),
    )
    if not plan_project:
        raise HTTPException(status_code=404, detail="Plan project not found")

    political_pack = _read_yaml(_spec_root() / "framing" / "POLITICAL_FRAMINGS.yaml")
    framings = political_pack.get("political_framings") if isinstance(political_pack, dict) else []
    available_ids = [f.get("political_framing_id") for f in framings if isinstance(f, dict) and f.get("political_framing_id")]
    if body.political_framing_ids:
        framing_ids = [fid for fid in body.political_framing_ids if fid in available_ids]
    else:
        max_framings = max(1, min(int(os.environ.get("TPA_SCENARIO_MAX_FRAMINGS", "3")), 6))
        framing_ids = available_ids[:max_framings]

    if not framing_ids:
        raise HTTPException(status_code=400, detail="No political framing ids available for scenario set")

    counts = {
        "evidence_items": _db_fetch_one(
            "SELECT COUNT(*) AS count FROM evidence_items WHERE plan_project_id = %s::uuid",
            (body.plan_project_id,),
        ),
        "sites_confirmed": _db_fetch_one(
            "SELECT COUNT(*) AS count FROM sites WHERE metadata->>'plan_project_id' = %s",
            (body.plan_project_id,),
        ),
        "visual_assets": _db_fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM visual_assets va
            LEFT JOIN documents d ON d.id = va.document_id
            WHERE va.metadata->>'plan_project_id' = %s
               OR d.authority_id = %s
            """,
            (body.plan_project_id, plan_project["authority_id"]),
        ),
    }
    count_payload = {k: (v.get("count") if isinstance(v, dict) else 0) for k, v in counts.items()}

    scenario_prompt = (
        "You are generating spatial strategy scenarios for a local plan. Return ONLY JSON.\n"
        "Output shape:\n"
        "{ \"scenarios\": [ { \"title\": string, \"summary\": string, \"state_vector\": object } ] }\n"
        "Generate 1-4 distinct scenarios with clear differentiators in the state_vector.\n"
    )
    user_payload = {
        "plan_project": {
            "plan_project_id": str(plan_project["id"]),
            "authority_id": plan_project["authority_id"],
            "title": plan_project["title"],
            "current_stage_id": plan_project.get("current_stage_id"),
        },
        "counts": count_payload,
        "prompt": body.prompt or "",
        "scenario_count": body.scenario_count,
    }

    scenarios_obj, tool_run_id, errs = _llm_structured_sync(
        prompt_id="scenario_auto_builder_v1",
        prompt_version=1,
        prompt_name="Scenario Auto Builder",
        purpose="Generate initial spatial strategy scenario options.",
        system_template=scenario_prompt,
        user_payload=user_payload,
        time_budget_seconds=60.0,
        temperature=0.6,
        max_tokens=1600,
        output_schema_ref="schemas/ScenarioAutoSet.schema.json",
    )

    scenarios_list = []
    if isinstance(scenarios_obj, dict):
        raw = scenarios_obj.get("scenarios")
        if isinstance(raw, list):
            scenarios_list = raw

    if not scenarios_list:
        scenarios_list = [
            {"title": "Baseline", "summary": "Baseline spatial strategy informed by existing evidence.", "state_vector": {}}
        ]

    scenario_ids: list[str] = []
    now = _utc_now()
    for item in scenarios_list[: body.scenario_count]:
        title = item.get("title") if isinstance(item, dict) and isinstance(item.get("title"), str) else "Scenario"
        summary = item.get("summary") if isinstance(item, dict) and isinstance(item.get("summary"), str) else ""
        state_vector = item.get("state_vector") if isinstance(item, dict) and isinstance(item.get("state_vector"), dict) else {}
        scenario_id = str(uuid4())
        scenario_ids.append(scenario_id)
        _db_execute(
            """
            INSERT INTO scenarios (
              id, plan_project_id, culp_stage_id, title, summary,
              state_vector_jsonb, parent_scenario_id, status, created_by,
              created_at, updated_at
            )
            VALUES (%s, %s::uuid, %s, %s, %s, %s::jsonb, NULL, %s, %s, %s, %s)
            """,
            (
                scenario_id,
                body.plan_project_id,
                body.culp_stage_id,
                title,
                summary,
                json.dumps(state_vector, ensure_ascii=False),
                "draft",
                "system",
                now,
                now,
            ),
        )

    _audit_event(
        event_type="scenario_auto_generated",
        plan_project_id=body.plan_project_id,
        culp_stage_id=body.culp_stage_id,
        payload={"scenario_ids": scenario_ids, "tool_run_id": tool_run_id, "errors": errs[:5]},
    )

    return create_scenario_set(
        ScenarioSetCreate(
            plan_project_id=body.plan_project_id,
            culp_stage_id=body.culp_stage_id,
            scenario_ids=scenario_ids,
            political_framing_ids=framing_ids,
        )
    )


def get_scenario_set(scenario_set_id: str) -> JSONResponse:
    row = _db_fetch_one(
        """
        SELECT id, plan_project_id, culp_stage_id, political_framing_ids_jsonb, scenario_ids_jsonb, tab_ids_jsonb,
               selected_tab_id, selection_rationale, selected_at
        FROM scenario_sets
        WHERE id = %s
        """,
        (scenario_set_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="ScenarioSet not found")

    tabs = _db_fetch_all(
        """
        SELECT t.id, t.scenario_set_id, t.scenario_id, t.political_framing_id, t.framing_id, t.run_id, t.status,
               t.trajectory_id, t.judgement_sheet_ref, t.updated_at,
               s.title AS scenario_title, s.summary AS scenario_summary
        FROM scenario_framing_tabs t
        JOIN scenarios s ON s.id = t.scenario_id
        WHERE t.scenario_set_id = %s
        ORDER BY t.updated_at DESC
        """,
        (scenario_set_id,),
    )

    return JSONResponse(
        content=jsonable_encoder(
            {
                "scenario_set": {
                    "scenario_set_id": str(row["id"]),
                    "plan_project_id": str(row["plan_project_id"]),
                    "culp_stage_id": row["culp_stage_id"],
                    "political_framing_ids": row["political_framing_ids_jsonb"] or [],
                    "scenario_ids": row["scenario_ids_jsonb"] or [],
                    "tab_ids": row["tab_ids_jsonb"] or [],
                    "selected_tab_id": row["selected_tab_id"],
                    "selection_rationale": row["selection_rationale"],
                    "selected_at": row["selected_at"],
                },
                "tabs": [
                    {
                        "tab_id": str(t["id"]),
                        "scenario_set_id": str(t["scenario_set_id"]),
                        "scenario_id": str(t["scenario_id"]),
                        "political_framing_id": t["political_framing_id"],
                        "framing_id": t["framing_id"],
                        "run_id": t["run_id"],
                        "status": t["status"],
                        "trajectory_id": t["trajectory_id"],
                        "judgement_sheet_ref": t["judgement_sheet_ref"],
                        "last_updated_at": t["updated_at"],
                        "scenario_title": t.get("scenario_title"),
                        "scenario_summary": t.get("scenario_summary") or "",
                    }
                    for t in tabs
                ],
            }
        )
    )


class ScenarioTabSelection(BaseModel):
    tab_id: str
    selection_rationale: str | None = None


def select_scenario_tab(scenario_set_id: str, body: ScenarioTabSelection) -> JSONResponse:
    now = _utc_now()
    _db_execute(
        """
        UPDATE scenario_sets
        SET selected_tab_id = %s, selection_rationale = %s, selected_at = %s
        WHERE id = %s
        """,
        (body.tab_id, body.selection_rationale, now, scenario_set_id),
    )

    row = _db_fetch_one("SELECT plan_project_id, culp_stage_id FROM scenario_sets WHERE id = %s", (scenario_set_id,))
    if row:
        _audit_event(
            event_type="scenario_tab_selected",
            plan_project_id=str(row["plan_project_id"]),
            culp_stage_id=row["culp_stage_id"],
            payload={"scenario_set_id": scenario_set_id, "tab_id": body.tab_id, "rationale": body.selection_rationale},
        )
    return get_scenario_set(scenario_set_id)


class ScenarioTabRunRequest(BaseModel):
    time_budget_seconds: float = Field(default=120.0, ge=5.0, le=900.0)
    max_issues: int = Field(default=6, ge=2, le=12)
    evidence_per_issue: int = Field(default=4, ge=1, le=10)
    context_token_budget: int = Field(
        default=128000,
        ge=4096,
        le=200000,
        description="Advisory input context budget for Context Assembly (input tokens, not output tokens).",
    )


def _insert_move_event(
    *,
    run_id: str,
    move_type: str,
    sequence: int,
    status: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    evidence_refs_considered: list[str],
    assumptions_introduced: list[dict[str, Any]],
    uncertainty_remaining: list[str],
    tool_run_ids: list[str],
) -> str:
    move_event_id = str(uuid4())
    now = _utc_now()
    _db_execute(
        """
        INSERT INTO move_events (
          id, run_id, move_type, sequence, status, created_at, started_at, ended_at,
          backtracked_from_move_id, backtrack_reason,
          inputs_jsonb, outputs_jsonb, evidence_refs_considered_jsonb, assumptions_introduced_jsonb,
          uncertainty_remaining_jsonb, tool_run_ids_jsonb
        )
        VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, NULL, NULL,
                %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
        """,
        (
            move_event_id,
            run_id,
            move_type,
            sequence,
            status,
            now,
            now,
            now,
            json.dumps(inputs, ensure_ascii=False),
            json.dumps(outputs, ensure_ascii=False),
            json.dumps(evidence_refs_considered[:200], ensure_ascii=False),
            json.dumps(assumptions_introduced, ensure_ascii=False),
            json.dumps(uncertainty_remaining[:20], ensure_ascii=False),
            json.dumps(tool_run_ids, ensure_ascii=False),
        ),
    )
    return move_event_id


def _link_evidence_to_move(
    *,
    run_id: str,
    move_event_id: str,
    evidence_refs: list[str],
    role: str,
) -> None:
    seen: set[tuple[str, str, str]] = set()
    now = _utc_now()
    for evidence_ref in evidence_refs:
        evidence_ref_id = _ensure_evidence_ref_row(evidence_ref)
        if not evidence_ref_id:
            continue
        key = (move_event_id, evidence_ref_id, role)
        if key in seen:
            continue
        seen.add(key)
        _db_execute(
            """
            INSERT INTO reasoning_evidence_links (id, run_id, move_event_id, evidence_ref_id, role, note, created_at)
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, NULL, %s)
            """,
            (str(uuid4()), run_id, move_event_id, evidence_ref_id, role, now),
        )


def _build_evidence_cards_from_atoms(evidence_atoms: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for atom in evidence_atoms[: max(1, min(limit, 12))]:
        ref = atom.get("evidence_ref")
        if not isinstance(ref, str):
            continue
        title = atom.get("title") if isinstance(atom.get("title"), str) else "Evidence"
        summary = atom.get("summary") if isinstance(atom.get("summary"), str) else ""
        card: dict[str, Any] = {
            "card_id": str(uuid4()),
            "card_type": "document",
            "title": title,
            "summary": summary,
            "evidence_refs": [ref],
            "limitations_text": atom.get("limitations_text") if isinstance(atom.get("limitations_text"), str) else "",
        }
        artifact_ref = atom.get("artifact_ref")
        if isinstance(artifact_ref, str) and artifact_ref:
            card["artifact_ref"] = artifact_ref
        cards.append(card)
    return cards


def run_scenario_framing_tab(tab_id: str, body: ScenarioTabRunRequest | None = None) -> JSONResponse:
    body = body or ScenarioTabRunRequest()

    tab = _db_fetch_one(
        """
        SELECT
          t.id AS tab_id,
          t.scenario_set_id,
          t.scenario_id,
          t.political_framing_id,
          t.status AS tab_status,
          ss.plan_project_id,
          ss.culp_stage_id,
          s.title AS scenario_title,
          s.summary AS scenario_summary,
          s.state_vector_jsonb,
          s.updated_at AS scenario_updated_at,
          pp.authority_id,
          pp.metadata_jsonb->>'plan_cycle_id' AS plan_cycle_id,
          pp.updated_at AS plan_project_updated_at
        FROM scenario_framing_tabs t
        JOIN scenario_sets ss ON ss.id = t.scenario_set_id
        JOIN scenarios s ON s.id = t.scenario_id
        JOIN plan_projects pp ON pp.id = ss.plan_project_id
        WHERE t.id = %s::uuid
        """,
        (tab_id,),
    )
    if not tab:
        raise HTTPException(status_code=404, detail="ScenarioFramingTab not found")

    authority_id = tab["authority_id"]
    plan_cycle_id = tab.get("plan_cycle_id")

    # Framing preset from spec pack.
    political_pack = _read_yaml(_spec_root() / "framing" / "POLITICAL_FRAMINGS.yaml")
    framing_presets = political_pack.get("political_framings") if isinstance(political_pack, dict) else []
    framing_preset = None
    for f in framing_presets or []:
        if isinstance(f, dict) and f.get("political_framing_id") == tab["political_framing_id"]:
            framing_preset = f
            break

    scenario_title = tab.get("scenario_title") or "Scenario"
    scenario_summary = tab.get("scenario_summary") or ""
    framing_title = (framing_preset or {}).get("title") or tab["political_framing_id"]

    run_id = str(uuid4())
    now = _utc_now()
    _db_execute(
        """
        INSERT INTO runs (id, profile, culp_stage_id, anchors_jsonb, created_at)
        VALUES (%s, %s, %s, %s::jsonb, %s)
        """,
        (
            run_id,
            os.environ.get("TPA_PROFILE", "oss"),
            tab.get("culp_stage_id"),
            json.dumps(
                {
                    "tab_id": str(tab["tab_id"]),
                    "scenario_set_id": str(tab["scenario_set_id"]),
                    "scenario_id": str(tab["scenario_id"]),
                    "political_framing_id": tab["political_framing_id"],
                    "plan_project_id": str(tab["plan_project_id"]),
                    "authority_id": authority_id,
                    "plan_cycle_id": plan_cycle_id,
                },
                ensure_ascii=False,
            ),
            now,
        ),
    )

    _audit_event(
        event_type="scenario_tab_run_started",
        run_id=run_id,
        plan_project_id=str(tab["plan_project_id"]),
        culp_stage_id=tab.get("culp_stage_id"),
        scenario_id=str(tab["scenario_id"]),
        payload={"tab_id": str(tab["tab_id"]), "political_framing_id": tab["political_framing_id"]},
    )
    _db_execute(
        """
        UPDATE scenario_framing_tabs
        SET status = %s, last_run_started_at = %s, updated_at = %s
        WHERE id = %s::uuid
        """,
        ("running", now, now, str(tab["tab_id"])),
    )

    sequence = 1
    all_uncertainties: list[str] = []
    all_tool_runs: list[str] = []

    # --- Move 1: Framing (mostly deterministic; assumptions are explicit)
    framing_obj = {
        "frame_id": str(uuid4()),
        "frame_title": f"{scenario_title} · {framing_title}",
        "political_framing_id": tab["political_framing_id"],
        "purpose": "Form a planner-legible position for the selected spatial strategy scenario under an explicit political framing.",
        "scope": {
            "area": authority_id,
            "sites": [],
            "time_horizon": tab.get("culp_stage_id") or "plan_period",
        },
        "decision_audience": "planner",
        "explicit_goals": (framing_preset or {}).get("default_goals") or [],
        "explicit_constraints": (framing_preset or {}).get("default_constraints") or [],
        "non_goals": (framing_preset or {}).get("non_goals") or [],
    }
    assumptions: list[dict[str, Any]] = []
    framing_move_id = _insert_move_event(
        run_id=run_id,
        move_type="framing",
        sequence=sequence,
        status="success",
        inputs={
            "scenario_id": str(tab["scenario_id"]),
            "scenario_title": scenario_title,
            "political_framing_id": tab["political_framing_id"],
            "culp_stage_id": tab.get("culp_stage_id"),
        },
        outputs={"framing": framing_obj, "assumptions": assumptions},
        evidence_refs_considered=[],
        assumptions_introduced=assumptions,
        uncertainty_remaining=[],
        tool_run_ids=[],
    )
    sequence += 1

    # --- Move 2: Issue surfacing (LLM-assisted; seeded by quick retrieval)
    issue_retrieval = _retrieve_chunks_hybrid_sync(
        query=f"{scenario_title}. {scenario_summary}".strip(),
        authority_id=authority_id,
        plan_cycle_id=plan_cycle_id,
        limit=10,
        rerank=True,
        rerank_top_n=15,
    )
    issue_tool_ids = [issue_retrieval.get("tool_run_id"), issue_retrieval.get("rerank_tool_run_id")]
    issue_tool_ids = [t for t in issue_tool_ids if isinstance(t, str)]
    all_tool_runs.extend(issue_tool_ids)
    seed_evidence = issue_retrieval.get("results") if isinstance(issue_retrieval, dict) else []
    seed_evidence_refs = [r.get("evidence_ref") for r in seed_evidence if isinstance(r, dict)]
    seed_evidence_refs = [r for r in seed_evidence_refs if isinstance(r, str)]

    per_call_budget = max(6.0, float(body.time_budget_seconds) / 6.0)
    issue_prompt = (
        "You are the Scout agent for The Planner's Assistant.\n"
        "Task: Surface the material planning issues for the scenario under the political framing.\n"
        "Return ONLY valid JSON: {\"issues\": [...], \"issue_map\": {...}}.\n"
        "Each issue: {\"title\": string, \"why_material\": string, \"initial_evidence_hooks\": [EvidenceRef...], "
        "\"uncertainty_flags\": [string...] }.\n"
        "IssueMap: {\"edges\": []} is acceptable.\n"
        "Use EvidenceRef strings provided; do not invent citations.\n"
        "Do not include markdown fences."
    )
    issue_json, issue_llm_tool_run_id, issue_errs = _llm_structured_sync(
        prompt_id="orchestrator.issue_surfacing",
        prompt_version=1,
        prompt_name="Issue surfacing (spatial strategy)",
        purpose="Abductively surface material issues under a political framing.",
        system_template=issue_prompt,
        user_payload={
            "scenario": {
                "title": scenario_title,
                "summary": scenario_summary,
                "state_vector": tab.get("state_vector_jsonb") or {},
            },
            "framing": framing_obj,
            "seed_evidence": [
                {
                    "evidence_ref": r.get("evidence_ref"),
                    "document_title": r.get("document_title"),
                    "page_number": r.get("page_number"),
                    "snippet": r.get("snippet"),
                }
                for r in (seed_evidence or [])[:10]
                if isinstance(r, dict)
            ],
            "max_issues": body.max_issues,
        },
        time_budget_seconds=per_call_budget,
        temperature=0.7,
        max_tokens=1100,
        output_schema_ref="schemas/Issue.schema.json",
    )
    if issue_llm_tool_run_id:
        issue_tool_ids.append(issue_llm_tool_run_id)
        all_tool_runs.append(issue_llm_tool_run_id)

    issues_raw = issue_json.get("issues") if isinstance(issue_json, dict) else None
    issues: list[dict[str, Any]] = []
    if isinstance(issues_raw, list):
        for i in issues_raw[: body.max_issues]:
            if not isinstance(i, dict):
                continue
            title = i.get("title")
            why = i.get("why_material")
            hooks = i.get("initial_evidence_hooks")
            if not isinstance(title, str) or not title.strip():
                continue
            if not isinstance(why, str) or not why.strip():
                why = "Material to the selected framing and scenario."
            if not isinstance(hooks, list):
                hooks = []
            clean_hooks = [h for h in hooks if isinstance(h, str) and "::" in h]
            if not clean_hooks:
                clean_hooks = seed_evidence_refs[:2]
            issues.append(
                {
                    "issue_id": str(uuid4()),
                    "title": title.strip(),
                    "why_material": why.strip(),
                    "initial_evidence_hooks": clean_hooks[:8],
                    "uncertainty_flags": [u for u in (i.get("uncertainty_flags") or []) if isinstance(u, str)][:8]
                    if isinstance(i.get("uncertainty_flags"), list)
                    else [],
                    "related_issues": [],
                }
            )

    if not issues:
        issues = [
            {
                "issue_id": str(uuid4()),
                "title": "Deliverability and infrastructure capacity",
                "why_material": "Whether the scenario can be delivered within the plan period with credible infrastructure pathways.",
                "initial_evidence_hooks": seed_evidence_refs[:3],
                "uncertainty_flags": ["Infrastructure evidence may be incomplete."],
                "related_issues": [],
            },
            {
                "issue_id": str(uuid4()),
                "title": "Environmental and flood constraints",
                "why_material": "Whether growth locations trigger significant environmental constraints and what mitigation would be required.",
                "initial_evidence_hooks": seed_evidence_refs[1:4],
                "uncertainty_flags": ["Constraint layers and plan maps not yet ingested."],
                "related_issues": [],
            },
            {
                "issue_id": str(uuid4()),
                "title": "Accessibility and transport impacts",
                "why_material": "Whether the scenario aligns with sustainable transport and avoids severe residual impacts.",
                "initial_evidence_hooks": seed_evidence_refs[:2],
                "uncertainty_flags": ["Transport evidence/instruments not yet run."],
                "related_issues": [],
            },
        ]

    issue_map = {"issue_map_id": str(uuid4()), "edges": []}

    issue_move_id = _insert_move_event(
        run_id=run_id,
        move_type="issue_surfacing",
        sequence=sequence,
        status="success" if not issue_errs else "partial",
        inputs={"framing": framing_obj, "seed_retrieval_tool_run_id": issue_retrieval.get("tool_run_id")},
        outputs={"issues": issues, "issue_map": issue_map},
        evidence_refs_considered=seed_evidence_refs,
        assumptions_introduced=[],
        uncertainty_remaining=["Issue surfacing is provisional; may shift after targeted evidence curation."],
        tool_run_ids=issue_tool_ids,
    )
    _link_evidence_to_move(run_id=run_id, move_event_id=issue_move_id, evidence_refs=seed_evidence_refs, role="contextual")
    sequence += 1

    # --- Move 3: Evidence curation (Context Assembly v1)
    context_deps = ContextAssemblyDeps(
        db_fetch_one=_db_fetch_one,
        db_fetch_all=_db_fetch_all,
        db_execute=_db_execute,
        llm_structured_sync=_llm_structured_sync,
        retrieve_chunks_hybrid_sync=_retrieve_chunks_hybrid_sync,
        retrieve_policy_clauses_hybrid_sync=_retrieve_policy_clauses_hybrid_sync,
        utc_now_iso=_utc_now_iso,
        utc_now=_utc_now,
    )
    context_result = assemble_curated_evidence_set_sync(
        deps=context_deps,
        run_id=run_id,
        work_mode="plan_studio",
        culp_stage_id=tab.get("culp_stage_id"),
        authority_id=authority_id,
        plan_cycle_id=plan_cycle_id,
        scenario={
            "scenario_id": str(tab["scenario_id"]),
            "title": scenario_title,
            "summary": scenario_summary,
            "state_vector": tab.get("state_vector_jsonb") or {},
        },
        framing={
            "political_framing_id": tab["political_framing_id"],
            "title": framing_title,
            "preset": framing_preset or {},
            "framing": framing_obj,
        },
        issues=issues,
        evidence_per_issue=body.evidence_per_issue,
        token_budget=body.context_token_budget,
        time_budget_seconds=body.time_budget_seconds,
    )

    curated_set = context_result.get("curated_evidence_set") if isinstance(context_result, dict) else None
    if not isinstance(curated_set, dict):
        curated_set = {
            "curated_evidence_set_id": str(uuid4()),
            "evidence_atoms": [],
            "evidence_by_issue": [],
            "deliberate_omissions": [],
            "tool_requests": [],
        }

    evidence_atoms = curated_set.get("evidence_atoms") if isinstance(curated_set.get("evidence_atoms"), list) else []
    curation_tool_run_ids = context_result.get("tool_run_ids") if isinstance(context_result.get("tool_run_ids"), list) else []
    curation_tool_run_ids = [t for t in curation_tool_run_ids if isinstance(t, str)]
    all_tool_runs.extend(curation_tool_run_ids)

    curated_evidence_refs = [a.get("evidence_ref") for a in evidence_atoms if isinstance(a, dict)]
    curated_evidence_refs = [r for r in curated_evidence_refs if isinstance(r, str)]

    curation_errors = context_result.get("selection_errors") if isinstance(context_result, dict) else None
    curation_errors = curation_errors if isinstance(curation_errors, list) else []
    curation_status = "success"
    if not evidence_atoms:
        curation_status = "error"
    elif curation_errors:
        curation_status = "partial"

    curation_move_id = _insert_move_event(
        run_id=run_id,
        move_type="evidence_curation",
        sequence=sequence,
        status=curation_status,
        inputs={
            "issues": issues,
            "retrieval": {"plan_cycle_id": plan_cycle_id, "authority_id": authority_id},
            "retrieval_frame_id": (context_result.get("retrieval_frame") or {}).get("retrieval_frame_id")
            if isinstance(context_result, dict) and isinstance(context_result.get("retrieval_frame"), dict)
            else None,
        },
        outputs={
            "curated_evidence_set": curated_set,
            "retrieval_frame": context_result.get("retrieval_frame") if isinstance(context_result, dict) else None,
            "context_assembly_errors": curation_errors[:10],
        },
        evidence_refs_considered=curated_evidence_refs,
        assumptions_introduced=[],
        uncertainty_remaining=[
            "Curated evidence is limited to authority pack PDFs and may omit datasets/appeals.",
            "Evidence selection is LLM-assisted and normatively framed; planners may disagree about what is countervailing.",
        ],
        tool_run_ids=curation_tool_run_ids,
    )
    if isinstance(context_result, dict) and isinstance(context_result.get("evidence_roles"), dict):
        roles = context_result.get("evidence_roles") or {}
        for role in ("supporting", "countervailing", "contextual"):
            evs = roles.get(role)
            if isinstance(evs, list):
                _link_evidence_to_move(
                    run_id=run_id,
                    move_event_id=curation_move_id,
                    evidence_refs=[e for e in evs if isinstance(e, str)],
                    role=role,
                )
    else:
        _link_evidence_to_move(run_id=run_id, move_event_id=curation_move_id, evidence_refs=curated_evidence_refs, role="supporting")
    sequence += 1

    # Persist ToolRequests so they become executable evidence-gathering (not just JSON in MoveEvent outputs).
    try:
        tool_requests_payload = curated_set.get("tool_requests") if isinstance(curated_set, dict) else None
        tool_requests_payload = tool_requests_payload if isinstance(tool_requests_payload, list) else []
        persist_tool_requests_for_move(run_id=run_id, move_event_id=curation_move_id, tool_requests=tool_requests_payload)
    except Exception:  # noqa: BLE001
        pass

    # --- Move 4: Evidence interpretation (LLM-assisted)
    interp_prompt = (
        "You are the Analyst agent for The Planner's Assistant.\n"
        "Interpret evidence atoms into caveated claims.\n"
        "Return ONLY valid JSON: {\"interpretations\": [...]}.\n"
        "Each interpretation: {\"claim\": string, \"evidence_refs\": [EvidenceRef...], \"limitations_text\": string}.\n"
        "Only use evidence_refs provided; do not invent citations.\n"
        "Do not include markdown fences."
    )
    interp_json, interp_tool_run_id, interp_errs = _llm_structured_sync(
        prompt_id="orchestrator.evidence_interpretation",
        prompt_version=1,
        prompt_name="Evidence interpretation (spatial strategy)",
        purpose="Turn curated evidence atoms into explicit interpretations with limitations.",
        system_template=interp_prompt,
        user_payload={
            "framing": framing_obj,
            "issues": [{"issue_id": i["issue_id"], "title": i["title"], "why_material": i["why_material"]} for i in issues],
            "evidence_atoms": [
                {
                    "evidence_ref": a.get("evidence_ref"),
                    "evidence_type": a.get("evidence_type"),
                    "title": a.get("title"),
                    "summary": a.get("summary"),
                    "excerpt_text": (a.get("metadata") or {}).get("excerpt_text") if isinstance(a.get("metadata"), dict) else None,
                    "limitations_text": a.get("limitations_text"),
                    "metadata": a.get("metadata") if isinstance(a.get("metadata"), dict) else {},
                }
                for a in evidence_atoms[:50]
            ],
        },
        time_budget_seconds=per_call_budget,
        temperature=0.6,
        max_tokens=1300,
        output_schema_ref="schemas/Interpretation.schema.json",
    )
    if interp_tool_run_id:
        all_tool_runs.append(interp_tool_run_id)

    interpretations: list[dict[str, Any]] = []
    interp_raw = interp_json.get("interpretations") if isinstance(interp_json, dict) else None
    if isinstance(interp_raw, list):
        for it in interp_raw[:20]:
            if not isinstance(it, dict):
                continue
            claim = it.get("claim")
            refs = it.get("evidence_refs")
            if not isinstance(claim, str) or not claim.strip():
                continue
            if not isinstance(refs, list):
                refs = []
            clean_refs = [r for r in refs if isinstance(r, str) and "::" in r][:10]
            if not clean_refs:
                continue
            interpretations.append(
                {
                    "interpretation_id": str(uuid4()),
                    "claim": claim.strip(),
                    "evidence_refs": clean_refs,
                    "assumptions_used": [],
                    "limitations_text": it.get("limitations_text") if isinstance(it.get("limitations_text"), str) else "",
                    "confidence": it.get("confidence") if isinstance(it.get("confidence"), (int, float)) else None,
                }
            )

    if not interpretations:
        interpretations = [
            {
                "interpretation_id": str(uuid4()),
                "claim": "Retrieved evidence indicates relevant policy/supporting text exists, but interpretation requires planner review.",
                "evidence_refs": curated_evidence_refs[:3],
                "assumptions_used": [],
                "limitations_text": "Fallback interpretation (LLM unavailable or failed).",
                "confidence": None,
            }
        ]

    interp_evidence_refs = sorted({r for it in interpretations for r in it.get("evidence_refs", []) if isinstance(r, str)})
    interp_tool_ids = [t for t in [interp_tool_run_id] if isinstance(t, str)]
    interpretation_move_id = _insert_move_event(
        run_id=run_id,
        move_type="evidence_interpretation",
        sequence=sequence,
        status="success" if not interp_errs else "partial",
        inputs={"curated_evidence_set_id": curated_set["curated_evidence_set_id"]},
        outputs={"interpretations": interpretations, "plan_reality_interpretations": [], "reasoning_traces": []},
        evidence_refs_considered=interp_evidence_refs,
        assumptions_introduced=[],
        uncertainty_remaining=["Interpretations are caveated and may omit spatial/visual evidence (Slice I pending)."],
        tool_run_ids=interp_tool_ids,
    )
    _link_evidence_to_move(
        run_id=run_id,
        move_event_id=interpretation_move_id,
        evidence_refs=interp_evidence_refs,
        role="supporting",
    )
    sequence += 1

    # --- Move 5: Considerations formation (LLM-assisted ledger)
    ledger_prompt = (
        "You are the Analyst agent for The Planner's Assistant.\n"
        "Form planner-recognisable considerations suitable for a ledger.\n"
        "Return ONLY valid JSON: {\"consideration_ledger_entries\": [...]}.\n"
        "Each entry: {\"statement\": string, \"premises\": [EvidenceRef...], \"mitigation_hooks\": [string...], "
        "\"uncertainty_list\": [string...] }.\n"
        "Only use premises from provided evidence_refs.\n"
        "Do not include markdown fences."
    )
    ledger_json, ledger_tool_run_id, ledger_errs = _llm_structured_sync(
        prompt_id="orchestrator.considerations_formation",
        prompt_version=1,
        prompt_name="Considerations formation (ledger)",
        purpose="Turn interpretations into consideration ledger entries with premises.",
        system_template=ledger_prompt,
        user_payload={
            "framing": framing_obj,
            "issues": [{"issue_id": i["issue_id"], "title": i["title"]} for i in issues],
            "interpretations": [{"claim": it["claim"], "evidence_refs": it["evidence_refs"]} for it in interpretations],
        },
        time_budget_seconds=per_call_budget,
        temperature=0.55,
        max_tokens=1500,
        output_schema_ref="schemas/ConsiderationLedgerEntry.schema.json",
    )
    if ledger_tool_run_id:
        all_tool_runs.append(ledger_tool_run_id)

    ledger_entries: list[dict[str, Any]] = []
    ledger_raw = ledger_json.get("consideration_ledger_entries") if isinstance(ledger_json, dict) else None
    if isinstance(ledger_raw, list):
        for e in ledger_raw[:30]:
            if not isinstance(e, dict):
                continue
            st = e.get("statement")
            premises = e.get("premises")
            if not isinstance(st, str) or not st.strip():
                continue
            if not isinstance(premises, list):
                premises = []
            clean_premises = [p for p in premises if isinstance(p, str) and "::" in p][:12]
            if not clean_premises:
                continue
            ledger_entries.append(
                {
                    "entry_id": str(uuid4()),
                    "statement": st.strip(),
                    "policy_clauses": e.get("policy_clauses") if isinstance(e.get("policy_clauses"), list) else [],
                    "premises": clean_premises,
                    "assumptions": [],
                    "mitigation_hooks": e.get("mitigation_hooks") if isinstance(e.get("mitigation_hooks"), list) else [],
                    "uncertainty_list": e.get("uncertainty_list") if isinstance(e.get("uncertainty_list"), list) else [],
                }
            )

    if not ledger_entries:
        ledger_entries = [
            {
                "entry_id": str(uuid4()),
                "statement": "Consideration: relevance and implications of retrieved policy text must be applied to the scenario.",
                "policy_clauses": [],
                "premises": interp_evidence_refs[:3],
                "assumptions": [],
                "mitigation_hooks": [],
                "uncertainty_list": ["Fallback ledger entry (LLM unavailable or failed)."],
            }
        ]

    # Optional: material consideration seam table population.
    for le in ledger_entries:
        try:
            _db_execute(
                """
                INSERT INTO material_considerations (
                  id, run_id, move_event_id, consideration_type, statement, evidence_refs_jsonb,
                  confidence_hint, uncertainty_note, created_at
                )
                VALUES (%s, %s::uuid, NULL, %s, %s, %s::jsonb, %s, %s, %s)
                """,
                (
                    str(uuid4()),
                    run_id,
                    "other",
                    le.get("statement"),
                    json.dumps(le.get("premises") or [], ensure_ascii=False),
                    None,
                    None,
                    _utc_now(),
                ),
            )
        except Exception:  # noqa: BLE001
            pass

    ledger_evidence_refs = sorted({r for le in ledger_entries for r in le.get("premises", []) if isinstance(r, str)})
    ledger_tool_ids = [t for t in [ledger_tool_run_id] if isinstance(t, str)]
    ledger_move_id = _insert_move_event(
        run_id=run_id,
        move_type="considerations_formation",
        sequence=sequence,
        status="success" if not ledger_errs else "partial",
        inputs={"interpretation_count": len(interpretations)},
        outputs={"consideration_ledger_entries": ledger_entries},
        evidence_refs_considered=ledger_evidence_refs,
        assumptions_introduced=[],
        uncertainty_remaining=[
            "PolicyClause parsing is LLM-assisted and non-deterministic; verify clause boundaries and legal weight against the source plan cycle."
        ],
        tool_run_ids=ledger_tool_ids,
    )
    _link_evidence_to_move(run_id=run_id, move_event_id=ledger_move_id, evidence_refs=ledger_evidence_refs, role="supporting")
    sequence += 1

    # --- Move 6: Weighing & balance (LLM-assisted)
    weighing_prompt = (
        "You are the Judge agent for The Planner's Assistant.\n"
        "Assign qualitative weights to considerations under the framing.\n"
        "Return ONLY valid JSON: {\"weighing_record\": {...}}.\n"
        "weighing_record must include: consideration_weights[{entry_id, weight, justification}], trade_offs[string], decisive_factors[entry_id], uncertainty_impact[string].\n"
        "Do not include markdown fences."
    )
    weighing_json, weighing_tool_run_id, weighing_errs = _llm_structured_sync(
        prompt_id="orchestrator.weighing_and_balance",
        prompt_version=1,
        prompt_name="Weighing & balance (qualitative)",
        purpose="Make trade-offs explicit and assign planner-shaped weight under a framing.",
        system_template=weighing_prompt,
        user_payload={
            "framing": framing_obj,
            "ledger_entries": [{"entry_id": le["entry_id"], "statement": le["statement"]} for le in ledger_entries],
        },
        time_budget_seconds=per_call_budget,
        temperature=0.55,
        max_tokens=1200,
        output_schema_ref="schemas/WeighingRecord.schema.json",
    )
    if weighing_tool_run_id:
        all_tool_runs.append(weighing_tool_run_id)

    weighing_record: dict[str, Any] | None = weighing_json.get("weighing_record") if isinstance(weighing_json, dict) else None
    if not isinstance(weighing_record, dict):
        weighing_record = None

    if weighing_record is None:
        weights = []
        for le in ledger_entries:
            weights.append({"entry_id": le["entry_id"], "weight": "moderate", "justification": "Fallback weighting."})
        weighing_record = {
            "weighing_id": str(uuid4()),
            "consideration_weights": weights,
            "trade_offs": [],
            "decisive_factors": [ledger_entries[0]["entry_id"]] if ledger_entries else [],
            "uncertainty_impact": "Uncertainty reduces confidence in the balance; further evidence would strengthen the position.",
        }
    else:
        weighing_record["weighing_id"] = str(uuid4())

    weighing_tool_ids = [t for t in [weighing_tool_run_id] if isinstance(t, str)]
    weighing_move_id = _insert_move_event(
        run_id=run_id,
        move_type="weighing_and_balance",
        sequence=sequence,
        status="success" if not weighing_errs else "partial",
        inputs={"ledger_entry_count": len(ledger_entries)},
        outputs={"weighing_record": weighing_record, "reasoning_traces": []},
        evidence_refs_considered=ledger_evidence_refs,
        assumptions_introduced=[],
        uncertainty_remaining=["Balance is qualitative; planners may reasonably disagree on weight."],
        tool_run_ids=weighing_tool_ids,
    )
    _link_evidence_to_move(run_id=run_id, move_event_id=weighing_move_id, evidence_refs=ledger_evidence_refs, role="contextual")
    sequence += 1

    # --- Move 7: Negotiation & alteration (LLM-assisted)
    negotiation_prompt = (
        "You are the Negotiator agent for The Planner's Assistant.\n"
        "Propose alterations/mitigations that could improve the balance.\n"
        "Return ONLY valid JSON: {\"negotiation_moves\": [...]}.\n"
        "Each move: {\"proposed_alterations\": [string...], \"addressed_considerations\": [entry_id...], \"validation_evidence_needed\": [string...] }.\n"
        "Do not include markdown fences."
    )
    negotiation_json, negotiation_tool_run_id, negotiation_errs = _llm_structured_sync(
        prompt_id="orchestrator.negotiation_and_alteration",
        prompt_version=1,
        prompt_name="Negotiation & alteration",
        purpose="Generate plausible alterations/mitigations with evidence needs.",
        system_template=negotiation_prompt,
        user_payload={
            "framing": framing_obj,
            "weighing_record": weighing_record,
            "ledger_entries": [{"entry_id": le["entry_id"], "statement": le["statement"]} for le in ledger_entries],
        },
        time_budget_seconds=per_call_budget,
        temperature=0.6,
        max_tokens=1100,
        output_schema_ref="schemas/NegotiationMove.schema.json",
    )
    if negotiation_tool_run_id:
        all_tool_runs.append(negotiation_tool_run_id)

    negotiation_moves: list[dict[str, Any]] = []
    neg_raw = negotiation_json.get("negotiation_moves") if isinstance(negotiation_json, dict) else None
    if isinstance(neg_raw, list):
        for m in neg_raw[:12]:
            if not isinstance(m, dict):
                continue
            alterations = m.get("proposed_alterations")
            addressed = m.get("addressed_considerations")
            if not isinstance(alterations, list) or not all(isinstance(x, str) for x in alterations):
                continue
            if not isinstance(addressed, list):
                addressed = []
            addressed_ids = [x for x in addressed if isinstance(x, str)]
            negotiation_moves.append(
                {
                    "negotiation_id": str(uuid4()),
                    "proposed_alterations": alterations[:10],
                    "addressed_considerations": addressed_ids[:20],
                    "validation_evidence_needed": m.get("validation_evidence_needed")
                    if isinstance(m.get("validation_evidence_needed"), list)
                    else [],
                }
            )

    if not negotiation_moves:
        negotiation_moves = [
            {
                "negotiation_id": str(uuid4()),
                "proposed_alterations": [],
                "addressed_considerations": [],
                "validation_evidence_needed": [],
            }
        ]

    negotiation_tool_ids = [t for t in [negotiation_tool_run_id] if isinstance(t, str)]
    negotiation_move_id = _insert_move_event(
        run_id=run_id,
        move_type="negotiation_and_alteration",
        sequence=sequence,
        status="success" if not negotiation_errs else "partial",
        inputs={"weighing_id": weighing_record.get("weighing_id")},
        outputs={"negotiation_moves": negotiation_moves},
        evidence_refs_considered=ledger_evidence_refs,
        assumptions_introduced=[],
        uncertainty_remaining=["Negotiation moves are proposals; viability requires evidence and political judgement."],
        tool_run_ids=negotiation_tool_ids,
    )
    sequence += 1

    # --- Move 8: Positioning & narration (LLM-assisted, but deterministic sheet composition)
    position_prompt = (
        "You are the Scribe agent for The Planner's Assistant.\n"
        "Write (1) a conditional position statement and (2) a concise planning balance narrative, both in UK planner tone.\n"
        "Return ONLY valid JSON: {\"position_statement\": string, \"planning_balance\": string, \"uncertainty_summary\": [string...] }.\n"
        "The position_statement must start with: \"Under framing ...\".\n"
        "Do not include markdown fences."
    )
    position_json, position_tool_run_id, position_errs = _llm_structured_sync(
        prompt_id="orchestrator.positioning_and_narration",
        prompt_version=1,
        prompt_name="Positioning & narration",
        purpose="Produce a conditional position and narratable balance statement.",
        system_template=position_prompt,
        user_payload={
            "scenario": {"title": scenario_title, "summary": scenario_summary},
            "framing": framing_obj,
            "weighing_record": weighing_record,
            "negotiation_moves": negotiation_moves,
        },
        time_budget_seconds=max(per_call_budget, 10.0),
        temperature=0.7,
        max_tokens=1400,
        output_schema_ref="schemas/Trajectory.schema.json",
    )
    if position_tool_run_id:
        all_tool_runs.append(position_tool_run_id)

    position_statement = (
        position_json.get("position_statement")
        if isinstance(position_json, dict) and isinstance(position_json.get("position_statement"), str)
        else None
    )
    planning_balance = (
        position_json.get("planning_balance")
        if isinstance(position_json, dict) and isinstance(position_json.get("planning_balance"), str)
        else None
    )
    uncertainty_summary = (
        position_json.get("uncertainty_summary")
        if isinstance(position_json, dict) and isinstance(position_json.get("uncertainty_summary"), list)
        else []
    )
    uncertainty_summary = [u for u in uncertainty_summary if isinstance(u, str)][:10]

    if not position_statement:
        position_statement = f"Under framing {framing_title}, a reasonable position is to treat '{scenario_title}' as a draft starting point, subject to evidence-led refinement."
    if not planning_balance:
        planning_balance = "Planning balance narrative is pending (LLM unavailable or failed)."

    evidence_cards = _build_evidence_cards_from_atoms(evidence_atoms, limit=6)
    figure_spec = None
    figure_tool_run_id = None
    figure_errors: list[str] = []
    figure_payload = {
        "scenario_title": scenario_title,
        "framing_title": framing_title,
        "issues": [{"title": i.get("title"), "why_material": i.get("why_material")} for i in issues[:6]],
        "evidence_atoms": [
            {
                "title": atom.get("title"),
                "summary": atom.get("summary"),
                "candidate_type": atom.get("candidate_type"),
                "metrics": atom.get("metrics"),
                "fingerprint": atom.get("fingerprint"),
                "instrument_output": atom.get("instrument_output"),
            }
            for atom in evidence_atoms[:6]
        ],
    }
    figure_prompt = (
        "You are generating a single planner-facing chart spec for a Scenario Judgement Sheet.\n"
        "Return ONLY JSON that matches FigureSpec.\n"
        "Use a simple bar chart with 3-6 bars and numeric values drawn from the evidence payload.\n"
        "If evidence lacks numbers, return an empty object {}.\n"
    )
    figure_spec, figure_tool_run_id, figure_errors = _llm_structured_sync(
        prompt_id="scenario_figure_spec_v1",
        prompt_version=1,
        prompt_name="Scenario Figure Spec",
        purpose="Generate a structured FigureSpec for a judgement sheet chart.",
        system_template=figure_prompt,
        user_payload=figure_payload,
        time_budget_seconds=25.0,
        temperature=0.2,
        max_tokens=600,
        output_schema_ref="schemas/FigureSpec.schema.json",
    )
    if figure_tool_run_id:
        all_tool_runs.append(figure_tool_run_id)
    if isinstance(figure_spec, dict) and figure_spec.get("series"):
        chart_obj, chart_tool_run_id, chart_errs = _run_render_simple_chart_sync(
            run_id=run_id,
            figure_spec=figure_spec,
            plan_project_id=str(tab["plan_project_id"]),
            scenario_id=str(tab["scenario_id"]),
        )
        figure_errors.extend(chart_errs)
        if chart_tool_run_id:
            all_tool_runs.append(chart_tool_run_id)
        if isinstance(chart_obj, dict) and chart_obj.get("artifact_path") and chart_obj.get("evidence_ref"):
            evidence_cards.append(
                {
                    "card_id": str(uuid4()),
                    "card_type": "chart",
                    "title": figure_spec.get("title") if isinstance(figure_spec.get("title"), str) else "Chart",
                    "summary": "Rendered chart from structured scenario evidence.",
                    "evidence_refs": [chart_obj["evidence_ref"]],
                    "artifact_ref": chart_obj["artifact_path"],
                    "limitations_text": "Chart values are derived from available evidence; verify source tables.",
                }
            )
    sheet = {
        "title": f"{scenario_title} × {framing_title}",
        "scenario": {"scenario_id": str(tab["scenario_id"]), "title": scenario_title},
        "framing": {
            "framing_id": framing_obj["frame_id"],
            "political_framing_id": tab["political_framing_id"],
            "frame_title": framing_obj["frame_title"],
        },
        "sections": {
            "framing_summary": framing_obj.get("purpose") or "",
            "scenario_summary": scenario_summary,
            "key_issues": [i["title"] for i in issues][:12],
            "evidence_cards": evidence_cards,
            "planning_balance": planning_balance,
            "conditional_position": position_statement,
            "uncertainty_summary": uncertainty_summary,
        },
    }

    trajectory_id = str(uuid4())
    trajectory_obj = {
        "trajectory_id": trajectory_id,
        "scenario_id": str(tab["scenario_id"]),
        "framing_id": framing_obj["frame_id"],
        "position_statement": position_statement,
        "explicit_assumptions": [],
        "key_evidence_refs": curated_evidence_refs[:20],
        "judgement_sheet_data": sheet,
    }

    # Persist trajectory and update tab.
    dependency_snapshot = _scenario_dependency_snapshot(tab)
    dependency_hash = stable_hash(dependency_snapshot)
    cache_expires_at = _utc_now() + timedelta(seconds=_SCENARIO_CACHE_TTL_SECONDS)
    _db_execute(
        """
        INSERT INTO trajectories (
          id, scenario_id, framing_id, position_statement,
          explicit_assumptions_jsonb, key_evidence_refs_jsonb, judgement_sheet_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
        """,
        (
            trajectory_id,
            str(tab["scenario_id"]),
            framing_obj["frame_id"],
            position_statement,
            json.dumps([], ensure_ascii=False),
            json.dumps(curated_evidence_refs[:50], ensure_ascii=False),
            json.dumps(sheet, ensure_ascii=False),
            _utc_now(),
        ),
    )
    cache_set_json(
        cache_key("scenario_sheet", str(tab["tab_id"]), dependency_hash),
        {
            "tab_id": str(tab["tab_id"]),
            "run_id": run_id,
            "status": "complete" if not position_errs else "partial",
            "trajectory": trajectory_obj,
            "sheet": sheet,
        },
        ttl_seconds=_SCENARIO_CACHE_TTL_SECONDS,
    )

    _db_execute(
        """
        UPDATE scenario_framing_tabs
        SET framing_id = %s, run_id = %s::uuid, status = %s, trajectory_id = %s::uuid,
            judgement_sheet_ref = %s, updated_at = %s, dependency_hash = %s,
            dependency_snapshot_jsonb = %s::jsonb, cache_expires_at = %s, last_run_completed_at = %s
        WHERE id = %s::uuid
        """,
        (
            framing_obj["frame_id"],
            run_id,
            "complete" if not position_errs else "partial",
            trajectory_id,
            f"trajectory::{trajectory_id}",
            _utc_now(),
            dependency_hash,
            json.dumps(dependency_snapshot, ensure_ascii=False),
            cache_expires_at,
            _utc_now(),
            str(tab["tab_id"]),
        ),
    )

    positioning_tool_ids = [t for t in [position_tool_run_id] if isinstance(t, str)]
    positioning_move_id = _insert_move_event(
        run_id=run_id,
        move_type="positioning_and_narration",
        sequence=sequence,
        status="success" if not position_errs else "partial",
        inputs={"scenario_id": str(tab["scenario_id"]), "political_framing_id": tab["political_framing_id"]},
        outputs={"trajectory": trajectory_obj, "scenario_judgement_sheet": sheet},
        evidence_refs_considered=curated_evidence_refs,
        assumptions_introduced=[],
        uncertainty_remaining=uncertainty_summary or ["Uncertainty remains; see evidence limitations and missing instruments."],
        tool_run_ids=positioning_tool_ids,
    )
    _link_evidence_to_move(run_id=run_id, move_event_id=positioning_move_id, evidence_refs=curated_evidence_refs[:50], role="supporting")

    _audit_event(
        event_type="scenario_tab_run_completed",
        run_id=run_id,
        plan_project_id=str(tab["plan_project_id"]),
        culp_stage_id=tab.get("culp_stage_id"),
        scenario_id=str(tab["scenario_id"]),
        payload={"tab_id": str(tab["tab_id"]), "status": "complete" if not position_errs else "partial"},
    )

    return JSONResponse(
        content=jsonable_encoder(
            {
                "tab_id": str(tab["tab_id"]),
                "run_id": run_id,
                "status": "complete" if not position_errs else "partial",
                "trajectory_id": trajectory_id,
                "sheet": sheet,
                "move_event_ids": [
                    framing_move_id,
                    issue_move_id,
                    curation_move_id,
                    interpretation_move_id,
                    ledger_move_id,
                    weighing_move_id,
                    negotiation_move_id,
                    positioning_move_id,
                ],
            }
        )
    )


def get_scenario_tab_sheet(tab_id: str, auto_refresh: bool = True, prefer_async: bool = True) -> JSONResponse:
    tab = _db_fetch_one(
        """
        SELECT
          t.id, t.scenario_id, t.political_framing_id, t.framing_id, t.run_id, t.status,
          t.trajectory_id, t.dependency_hash, t.dependency_snapshot_jsonb, t.cache_expires_at, t.last_run_completed_at,
          s.state_vector_jsonb, s.updated_at AS scenario_updated_at,
          ss.plan_project_id, ss.culp_stage_id,
          pp.authority_id, pp.metadata_jsonb->>'plan_cycle_id' AS plan_cycle_id,
          pp.updated_at AS plan_project_updated_at
        FROM scenario_framing_tabs t
        JOIN scenario_sets ss ON ss.id = t.scenario_set_id
        JOIN scenarios s ON s.id = t.scenario_id
        JOIN plan_projects pp ON pp.id = ss.plan_project_id
        WHERE t.id = %s::uuid
        """,
        (tab_id,),
    )
    if not tab:
        raise HTTPException(status_code=404, detail="ScenarioFramingTab not found")

    dependency_snapshot = _scenario_dependency_snapshot(tab)
    dependency_hash = stable_hash(dependency_snapshot)
    cache_expires_at = tab.get("cache_expires_at")
    is_expired = bool(cache_expires_at and cache_expires_at < _utc_now())
    is_stale = dependency_hash != (tab.get("dependency_hash") or "") or is_expired

    if not tab.get("trajectory_id"):
        if auto_refresh and tab.get("status") not in ("running", "queued"):
            if prefer_async:
                _schedule_tab_refresh(tab_id)
            else:
                return run_scenario_framing_tab(tab_id)
        return JSONResponse(
            content=jsonable_encoder(
                {
                    "tab_id": tab_id,
                    "status": tab.get("status"),
                    "trajectory": None,
                    "sheet": None,
                    "freshness": {
                        "dependency_hash": dependency_hash,
                        "is_stale": True,
                    "cache_expires_at": cache_expires_at,
                    "last_run_completed_at": tab.get("last_run_completed_at"),
                    "dependency_snapshot": tab.get("dependency_snapshot_jsonb") or {},
                    },
                }
            )
        )

    if is_stale and auto_refresh and tab.get("status") not in ("running", "queued"):
        if prefer_async:
            _schedule_tab_refresh(tab_id)
        else:
            return run_scenario_framing_tab(tab_id)

    if not is_stale:
        cached = cache_get_json(cache_key("scenario_sheet", tab_id, dependency_hash))
        if cached:
            cached["freshness"] = {
                "dependency_hash": dependency_hash,
                "is_stale": False,
                "cache_expires_at": cache_expires_at,
                "last_run_completed_at": tab.get("last_run_completed_at"),
                "dependency_snapshot": tab.get("dependency_snapshot_jsonb") or {},
            }
            cached["cached"] = True
            return JSONResponse(content=jsonable_encoder(cached))

    traj = _db_fetch_one(
        """
        SELECT id, scenario_id, framing_id, position_statement, explicit_assumptions_jsonb,
               key_evidence_refs_jsonb, judgement_sheet_jsonb, created_at
        FROM trajectories
        WHERE id = %s::uuid
        """,
        (str(tab["trajectory_id"]),),
    )
    if not traj:
        raise HTTPException(status_code=404, detail="Trajectory not found")

    trajectory = {
        "trajectory_id": str(traj["id"]),
        "scenario_id": str(traj["scenario_id"]),
        "framing_id": str(traj["framing_id"]),
        "position_statement": traj["position_statement"],
        "explicit_assumptions": traj["explicit_assumptions_jsonb"] or [],
        "key_evidence_refs": traj["key_evidence_refs_jsonb"] or [],
        "judgement_sheet_data": traj["judgement_sheet_jsonb"] or {},
    }

    response = {
        "tab_id": tab_id,
        "status": tab.get("status"),
        "run_id": tab.get("run_id"),
        "trajectory": trajectory,
        "sheet": traj["judgement_sheet_jsonb"] or {},
        "freshness": {
            "dependency_hash": dependency_hash,
            "is_stale": is_stale,
            "cache_expires_at": cache_expires_at,
            "last_run_completed_at": tab.get("last_run_completed_at"),
            "dependency_snapshot": tab.get("dependency_snapshot_jsonb") or {},
        },
    }
    if not is_stale:
        cache_set_json(
            cache_key("scenario_sheet", tab_id, dependency_hash),
            response,
            ttl_seconds=_SCENARIO_CACHE_TTL_SECONDS,
        )
    return JSONResponse(content=jsonable_encoder(response))
