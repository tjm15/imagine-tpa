from __future__ import annotations

import json
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import StateGraph, END

from tpa_api.context_assembly import ContextAssemblyDeps, assemble_curated_evidence_set_sync
from tpa_api.context_pack import ContextPackAssemblyDeps, build_context_pack_sync
from tpa_api.db import _db_execute, _db_fetch_all, _db_fetch_one
from tpa_api.evidence import _ensure_evidence_ref_row
from tpa_api.prompting import _llm_structured_sync
from tpa_api.retrieval import _retrieve_chunks_hybrid_sync, _retrieve_policy_clauses_hybrid_sync
from tpa_api.time_utils import _utc_now, _utc_now_iso
from tpa_api.tool_requests import persist_tool_requests_for_move


class GrammarState(TypedDict, total=False):
    run_id: str
    work_mode: str
    authority_id: str
    plan_cycle_id: str | None
    plan_project_id: str | None
    scenario_id: str | None
    application_id: str | None
    culp_stage_id: str | None
    political_framing_id: str | None
    framing_preset: dict[str, Any] | None
    scenario_title: str
    scenario_summary: str
    state_vector: dict[str, Any]
    context_token_budget: int
    max_issues: int
    sequence: int
    framing: dict[str, Any]
    issues: list[dict[str, Any]]
    issue_map: dict[str, Any]
    curated_evidence_set: dict[str, Any]
    evidence_atoms: list[dict[str, Any]]
    interpretations: list[dict[str, Any]]
    ledger_entries: list[dict[str, Any]]
    weighing_record: dict[str, Any]
    negotiation_moves: list[dict[str, Any]]
    trajectory: dict[str, Any]
    move_event_ids: list[str]


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


def _collect_context_pack_refs(context_pack: dict[str, Any] | None) -> list[str]:
    if not isinstance(context_pack, dict):
        return []
    slices = context_pack.get("slices") if isinstance(context_pack.get("slices"), dict) else {}
    refs: list[str] = []

    def add(ref: Any) -> None:
        if isinstance(ref, str) and "::" in ref:
            refs.append(ref)

    for slice_items in slices.values():
        if not isinstance(slice_items, list):
            continue
        for item in slice_items:
            if not isinstance(item, dict):
                continue
            if "evidence_ref" in item:
                add(item.get("evidence_ref"))
            if "evidence_refs" in item and isinstance(item.get("evidence_refs"), list):
                for ev in item.get("evidence_refs"):
                    add(ev)

    seen: set[str] = set()
    return [r for r in refs if not (r in seen or seen.add(r))]


def _build_evidence_cards(evidence_atoms: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for atom in evidence_atoms[: max(1, min(limit, 12))]:
        ref = atom.get("evidence_ref") if isinstance(atom, dict) else None
        if not isinstance(ref, str):
            continue
        title = atom.get("title") if isinstance(atom.get("title"), str) else "Evidence"
        summary = atom.get("summary") if isinstance(atom.get("summary"), str) else ""
        card: dict[str, Any] = {
            "card_id": str(uuid4()),
            "card_type": atom.get("type") if isinstance(atom.get("type"), str) else "document",
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


def _context_deps() -> tuple[ContextAssemblyDeps, ContextPackAssemblyDeps]:
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
    pack_deps = ContextPackAssemblyDeps(
        db_fetch_one=_db_fetch_one,
        db_fetch_all=_db_fetch_all,
        db_execute=_db_execute,
        llm_structured_sync=_llm_structured_sync,
        utc_now_iso=_utc_now_iso,
        utc_now=_utc_now,
    )
    return context_deps, pack_deps


def _build_context_pack(
    state: GrammarState,
    move: str,
    issues: list[dict[str, Any]],
    framing: dict[str, Any],
) -> dict[str, Any]:
    _, pack_deps = _context_deps()
    return build_context_pack_sync(
        deps=pack_deps,
        run_id=state["run_id"],
        move_type=move,
        work_mode=state.get("work_mode") or "plan_studio",
        authority_id=state.get("authority_id"),
        plan_cycle_id=state.get("plan_cycle_id"),
        plan_project_id=state.get("plan_project_id"),
        scenario_id=state.get("scenario_id"),
        application_id=state.get("application_id"),
        framing=framing,
        issues=issues or [],
        token_budget=state.get("context_token_budget"),
    )


def node_framing(state: GrammarState) -> GrammarState:
    framing_obj = state.get("framing")
    if not isinstance(framing_obj, dict):
        preset = state.get("framing_preset") if isinstance(state.get("framing_preset"), dict) else {}
        framing_title = preset.get("title") or state.get("political_framing_id") or "framing"
        framing_obj = {
            "frame_id": str(uuid4()),
            "frame_title": framing_title,
            "political_framing_id": state.get("political_framing_id"),
            "purpose": "Form a planner-legible position under an explicit political framing.",
            "scope": {"area": state.get("authority_id"), "sites": [], "time_horizon": state.get("culp_stage_id") or "plan_period"},
            "decision_audience": "planner",
            "explicit_goals": preset.get("default_goals") or [],
            "explicit_constraints": preset.get("default_constraints") or [],
            "non_goals": preset.get("non_goals") or [],
        }

    context_pack = _build_context_pack(state, "framing", [], framing_obj)
    refs = _collect_context_pack_refs(context_pack)
    sequence = int(state.get("sequence") or 1)
    move_id = _insert_move_event(
        run_id=state["run_id"],
        move_type="framing",
        sequence=sequence,
        status="success",
        inputs={"context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None},
        outputs={"framing": framing_obj, "assumptions": []},
        evidence_refs_considered=refs,
        assumptions_introduced=[],
        uncertainty_remaining=[],
        tool_run_ids=[],
    )
    state["framing"] = framing_obj
    state["sequence"] = sequence + 1
    state.setdefault("move_event_ids", []).append(move_id)
    return state


def node_issue_surfacing(state: GrammarState) -> GrammarState:
    framing_obj = state.get("framing") if isinstance(state.get("framing"), dict) else {}
    context_pack = _build_context_pack(state, "issue_surfacing", [], framing_obj)
    refs = _collect_context_pack_refs(context_pack)
    prompt = (
        "You are the Scout agent for The Planner's Assistant.\n"
        "Task: Surface the material planning issues for the scenario under the political framing.\n"
        "Return ONLY valid JSON: {\"issues\": [...], \"issue_map\": {...}}.\n"
        "Each issue: {\"title\": string, \"why_material\": string, \"initial_evidence_hooks\": [EvidenceRef...], "
        "\"uncertainty_flags\": [string...] }.\n"
        "IssueMap: {\"edges\": []} is acceptable.\n"
        "Use EvidenceRef strings provided in the ContextPack; do not invent citations.\n"
        "Do not include markdown fences."
    )
    issue_json, tool_run_id, errs = _llm_structured_sync(
        prompt_id="orchestrator.issue_surfacing",
        prompt_version=1,
        prompt_name="Issue surfacing (grammar)",
        purpose="Abductively surface material issues under a political framing.",
        system_template=prompt,
        user_payload={
            "scenario": {
                "title": state.get("scenario_title") or "Scenario",
                "summary": state.get("scenario_summary") or "",
                "state_vector": state.get("state_vector") or {},
            },
            "framing": framing_obj,
            "context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None,
            "context_pack": context_pack.get("slices") if isinstance(context_pack, dict) else {},
            "max_issues": state.get("max_issues") or 6,
        },
        output_schema_ref="schemas/Issue.schema.json",
    )

    issues_raw = issue_json.get("issues") if isinstance(issue_json, dict) else None
    issues: list[dict[str, Any]] = []
    if isinstance(issues_raw, list):
        for i in issues_raw[: int(state.get("max_issues") or 6)]:
            if not isinstance(i, dict):
                continue
            title = i.get("title")
            why = i.get("why_material")
            hooks = i.get("initial_evidence_hooks") if isinstance(i.get("initial_evidence_hooks"), list) else []
            if not isinstance(title, str) or not title.strip():
                continue
            issues.append(
                {
                    "issue_id": str(uuid4()),
                    "title": title.strip(),
                    "why_material": why.strip() if isinstance(why, str) and why.strip() else "Material to the framing.",
                    "initial_evidence_hooks": [h for h in hooks if isinstance(h, str) and "::" in h][:12] or refs[:2],
                    "uncertainty_flags": [
                        u for u in (i.get("uncertainty_flags") or []) if isinstance(u, str)
                    ][:8]
                    if isinstance(i.get("uncertainty_flags"), list)
                    else [],
                    "related_issues": [],
                }
            )
    if not issues:
        issues = [
            {
                "issue_id": str(uuid4()),
                "title": "Policy compliance and spatial constraints",
                "why_material": "Baseline issue surface when evidence is limited.",
                "initial_evidence_hooks": refs[:3],
                "uncertainty_flags": ["Issue surfacing fallback; expand with more evidence."],
                "related_issues": [],
            }
        ]

    issue_map = {"issue_map_id": str(uuid4()), "edges": []}
    sequence = int(state.get("sequence") or 1)
    tool_run_ids = [t for t in [tool_run_id] if isinstance(t, str)]
    move_id = _insert_move_event(
        run_id=state["run_id"],
        move_type="issue_surfacing",
        sequence=sequence,
        status="success" if not errs else "partial",
        inputs={"context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None},
        outputs={"issues": issues, "issue_map": issue_map},
        evidence_refs_considered=refs,
        assumptions_introduced=[],
        uncertainty_remaining=["Issue surfacing is provisional; may shift after evidence curation."],
        tool_run_ids=tool_run_ids,
    )
    _link_evidence_to_move(run_id=state["run_id"], move_event_id=move_id, evidence_refs=refs, role="contextual")
    state["issues"] = issues
    state["issue_map"] = issue_map
    state["sequence"] = sequence + 1
    state.setdefault("move_event_ids", []).append(move_id)
    return state


def node_evidence_curation(state: GrammarState) -> GrammarState:
    issues = state.get("issues") if isinstance(state.get("issues"), list) else []
    framing_obj = state.get("framing") if isinstance(state.get("framing"), dict) else {}
    context_pack = _build_context_pack(state, "evidence_curation", issues, framing_obj)
    refs = _collect_context_pack_refs(context_pack)

    context_deps, _ = _context_deps()
    context_result = assemble_curated_evidence_set_sync(
        deps=context_deps,
        run_id=state["run_id"],
        work_mode=state.get("work_mode"),
        culp_stage_id=state.get("culp_stage_id"),
        authority_id=state.get("authority_id"),
        plan_cycle_id=state.get("plan_cycle_id"),
        scenario={
            "scenario_id": state.get("scenario_id"),
            "title": state.get("scenario_title") or "Scenario",
            "summary": state.get("scenario_summary") or "",
            "state_vector": state.get("state_vector") or {},
        },
        framing={
            "political_framing_id": state.get("political_framing_id"),
            "title": framing_obj.get("frame_title") if isinstance(framing_obj, dict) else None,
            "preset": state.get("framing_preset") or {},
            "framing": framing_obj,
        },
        issues=issues,
        token_budget=state.get("context_token_budget"),
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
    curated_refs = [a.get("evidence_ref") for a in evidence_atoms if isinstance(a, dict)]
    curated_refs = [r for r in curated_refs if isinstance(r, str)]
    curation_errors = context_result.get("selection_errors") if isinstance(context_result, dict) else None
    curation_errors = curation_errors if isinstance(curation_errors, list) else []
    curation_status = "error" if not evidence_atoms else ("partial" if curation_errors else "success")

    sequence = int(state.get("sequence") or 1)
    move_id = _insert_move_event(
        run_id=state["run_id"],
        move_type="evidence_curation",
        sequence=sequence,
        status=curation_status,
        inputs={
            "issues": issues,
            "retrieval": {"plan_cycle_id": state.get("plan_cycle_id"), "authority_id": state.get("authority_id")},
            "retrieval_frame_id": (context_result.get("retrieval_frame") or {}).get("retrieval_frame_id")
            if isinstance(context_result, dict) and isinstance(context_result.get("retrieval_frame"), dict)
            else None,
            "context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None,
        },
        outputs={
            "curated_evidence_set": curated_set,
            "retrieval_frame": context_result.get("retrieval_frame") if isinstance(context_result, dict) else None,
            "context_assembly_errors": curation_errors[:10],
        },
        evidence_refs_considered=curated_refs + refs,
        assumptions_introduced=[],
        uncertainty_remaining=[
            "Curated evidence is limited to available authority packs and instruments.",
            "Evidence selection is LLM-assisted; planners may disagree about countervailing material.",
        ],
        tool_run_ids=[t for t in context_result.get("tool_run_ids") or [] if isinstance(t, str)],
    )
    _link_evidence_to_move(run_id=state["run_id"], move_event_id=move_id, evidence_refs=curated_refs, role="supporting")
    if refs:
        _link_evidence_to_move(run_id=state["run_id"], move_event_id=move_id, evidence_refs=refs, role="contextual")
    try:
        tool_requests_payload = curated_set.get("tool_requests") if isinstance(curated_set, dict) else None
        tool_requests_payload = tool_requests_payload if isinstance(tool_requests_payload, list) else []
        persist_tool_requests_for_move(run_id=state["run_id"], move_event_id=move_id, tool_requests=tool_requests_payload)
    except Exception:  # noqa: BLE001
        pass

    state["curated_evidence_set"] = curated_set
    state["evidence_atoms"] = evidence_atoms
    state["sequence"] = sequence + 1
    state.setdefault("move_event_ids", []).append(move_id)
    return state


def node_evidence_interpretation(state: GrammarState) -> GrammarState:
    issues = state.get("issues") if isinstance(state.get("issues"), list) else []
    framing_obj = state.get("framing") if isinstance(state.get("framing"), dict) else {}
    context_pack = _build_context_pack(state, "evidence_interpretation", issues, framing_obj)
    refs = _collect_context_pack_refs(context_pack)
    evidence_atoms = state.get("evidence_atoms") if isinstance(state.get("evidence_atoms"), list) else []

    prompt = (
        "You are the Analyst agent for The Planner's Assistant.\n"
        "Interpret evidence atoms into caveated claims.\n"
        "Return ONLY valid JSON: {\"interpretations\": [...]}.\n"
        "Each interpretation: {\"claim\": string, \"evidence_refs\": [EvidenceRef...], \"limitations_text\": string}.\n"
        "Only use evidence_refs provided in the ContextPack; do not invent citations.\n"
        "Do not include markdown fences."
    )
    interp_json, tool_run_id, errs = _llm_structured_sync(
        prompt_id="orchestrator.evidence_interpretation",
        prompt_version=1,
        prompt_name="Evidence interpretation (grammar)",
        purpose="Turn curated evidence atoms into explicit interpretations with limitations.",
        system_template=prompt,
        user_payload={
            "framing": framing_obj,
            "issues": [{"issue_id": i.get("issue_id"), "title": i.get("title")} for i in issues if isinstance(i, dict)],
            "context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None,
            "context_pack": context_pack.get("slices") if isinstance(context_pack, dict) else {},
            "evidence_atoms": evidence_atoms,
        },
        output_schema_ref="schemas/Interpretation.schema.json",
    )

    interpretations: list[dict[str, Any]] = []
    interp_raw = interp_json.get("interpretations") if isinstance(interp_json, dict) else None
    if isinstance(interp_raw, list):
        for it in interp_raw:
            if not isinstance(it, dict):
                continue
            claim = it.get("claim")
            refs_used = it.get("evidence_refs") if isinstance(it.get("evidence_refs"), list) else []
            if not isinstance(claim, str) or not claim.strip():
                continue
            clean_refs = [r for r in refs_used if isinstance(r, str) and "::" in r][:10]
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
                "claim": "Interpretations require planner review; evidence may be incomplete.",
                "evidence_refs": refs[:3],
                "assumptions_used": [],
                "limitations_text": "Fallback interpretation (LLM unavailable or failed).",
                "confidence": None,
            }
        ]

    interp_refs = sorted({r for it in interpretations for r in it.get("evidence_refs", []) if isinstance(r, str)})
    sequence = int(state.get("sequence") or 1)
    move_id = _insert_move_event(
        run_id=state["run_id"],
        move_type="evidence_interpretation",
        sequence=sequence,
        status="success" if not errs else "partial",
        inputs={"context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None},
        outputs={"interpretations": interpretations, "plan_reality_interpretations": [], "reasoning_traces": []},
        evidence_refs_considered=refs,
        assumptions_introduced=[],
        uncertainty_remaining=["Interpretations are caveated; verify spatial/visual evidence where relevant."],
        tool_run_ids=[t for t in [tool_run_id] if isinstance(t, str)],
    )
    _link_evidence_to_move(run_id=state["run_id"], move_event_id=move_id, evidence_refs=interp_refs, role="supporting")
    state["interpretations"] = interpretations
    state["sequence"] = sequence + 1
    state.setdefault("move_event_ids", []).append(move_id)
    return state


def node_considerations_formation(state: GrammarState) -> GrammarState:
    issues = state.get("issues") if isinstance(state.get("issues"), list) else []
    framing_obj = state.get("framing") if isinstance(state.get("framing"), dict) else {}
    interpretations = state.get("interpretations") if isinstance(state.get("interpretations"), list) else []
    context_pack = _build_context_pack(state, "considerations_formation", issues, framing_obj)
    refs = _collect_context_pack_refs(context_pack)

    prompt = (
        "You are the Analyst agent for The Planner's Assistant.\n"
        "Form planner-recognisable considerations suitable for a ledger.\n"
        "Return ONLY valid JSON: {\"consideration_ledger_entries\": [...]}.\n"
        "Each entry: {\"statement\": string, \"premises\": [EvidenceRef...], \"mitigation_hooks\": [string...], "
        "\"uncertainty_list\": [string...] }.\n"
        "Only use premises from provided evidence_refs in the ContextPack.\n"
        "Do not include markdown fences."
    )
    ledger_json, tool_run_id, errs = _llm_structured_sync(
        prompt_id="orchestrator.considerations_formation",
        prompt_version=1,
        prompt_name="Considerations formation (grammar)",
        purpose="Turn interpretations into consideration ledger entries with premises.",
        system_template=prompt,
        user_payload={
            "framing": framing_obj,
            "issues": [{"issue_id": i.get("issue_id"), "title": i.get("title")} for i in issues if isinstance(i, dict)],
            "interpretations": [{"claim": it.get("claim"), "evidence_refs": it.get("evidence_refs")} for it in interpretations],
            "context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None,
            "context_pack": context_pack.get("slices") if isinstance(context_pack, dict) else {},
        },
        output_schema_ref="schemas/ConsiderationLedgerEntry.schema.json",
    )

    ledger_entries: list[dict[str, Any]] = []
    ledger_raw = ledger_json.get("consideration_ledger_entries") if isinstance(ledger_json, dict) else None
    if isinstance(ledger_raw, list):
        for e in ledger_raw:
            if not isinstance(e, dict):
                continue
            st = e.get("statement")
            premises = e.get("premises") if isinstance(e.get("premises"), list) else []
            if not isinstance(st, str) or not st.strip():
                continue
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
                "statement": "Consideration: apply policy tests to scenario evidence.",
                "policy_clauses": [],
                "premises": refs[:3],
                "assumptions": [],
                "mitigation_hooks": [],
                "uncertainty_list": ["Fallback ledger entry (LLM unavailable or failed)."],
            }
        ]

    ledger_refs = sorted({r for le in ledger_entries for r in le.get("premises", []) if isinstance(r, str)})
    sequence = int(state.get("sequence") or 1)
    move_id = _insert_move_event(
        run_id=state["run_id"],
        move_type="considerations_formation",
        sequence=sequence,
        status="success" if not errs else "partial",
        inputs={"context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None},
        outputs={"consideration_ledger_entries": ledger_entries},
        evidence_refs_considered=refs,
        assumptions_introduced=[],
        uncertainty_remaining=["PolicyClause parsing is LLM-assisted; verify legal weight against source plan."],
        tool_run_ids=[t for t in [tool_run_id] if isinstance(t, str)],
    )
    _link_evidence_to_move(run_id=state["run_id"], move_event_id=move_id, evidence_refs=ledger_refs, role="supporting")
    state["ledger_entries"] = ledger_entries
    state["sequence"] = sequence + 1
    state.setdefault("move_event_ids", []).append(move_id)
    return state


def node_weighing_and_balance(state: GrammarState) -> GrammarState:
    framing_obj = state.get("framing") if isinstance(state.get("framing"), dict) else {}
    ledger_entries = state.get("ledger_entries") if isinstance(state.get("ledger_entries"), list) else []
    context_pack = _build_context_pack(state, "weighing_and_balance", state.get("issues") or [], framing_obj)
    refs = _collect_context_pack_refs(context_pack)

    prompt = (
        "You are the Judge agent for The Planner's Assistant.\n"
        "Assign qualitative weights to considerations under the framing.\n"
        "Return ONLY valid JSON: {\"weighing_record\": {...}}.\n"
        "weighing_record must include: consideration_weights[{entry_id, weight, justification}], trade_offs[string], decisive_factors[entry_id], uncertainty_impact[string].\n"
        "Do not include markdown fences."
    )
    weighing_json, tool_run_id, errs = _llm_structured_sync(
        prompt_id="orchestrator.weighing_and_balance",
        prompt_version=1,
        prompt_name="Weighing & balance (grammar)",
        purpose="Make trade-offs explicit and assign planner-shaped weight under a framing.",
        system_template=prompt,
        user_payload={
            "framing": framing_obj,
            "ledger_entries": [{"entry_id": le.get("entry_id"), "statement": le.get("statement")} for le in ledger_entries],
            "context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None,
            "context_pack": context_pack.get("slices") if isinstance(context_pack, dict) else {},
        },
        output_schema_ref="schemas/WeighingRecord.schema.json",
    )
    weighing_record = weighing_json.get("weighing_record") if isinstance(weighing_json, dict) else None
    if not isinstance(weighing_record, dict):
        weighing_record = {
            "weighing_id": str(uuid4()),
            "consideration_weights": [
                {"entry_id": le.get("entry_id"), "weight": "moderate", "justification": "Fallback weighting."}
                for le in ledger_entries
            ],
            "trade_offs": [],
            "decisive_factors": [ledger_entries[0]["entry_id"]] if ledger_entries else [],
            "uncertainty_impact": "Uncertainty reduces confidence in the balance.",
        }
    else:
        weighing_record["weighing_id"] = str(uuid4())

    sequence = int(state.get("sequence") or 1)
    move_id = _insert_move_event(
        run_id=state["run_id"],
        move_type="weighing_and_balance",
        sequence=sequence,
        status="success" if not errs else "partial",
        inputs={"context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None},
        outputs={"weighing_record": weighing_record, "reasoning_traces": []},
        evidence_refs_considered=refs,
        assumptions_introduced=[],
        uncertainty_remaining=["Balance is qualitative; planners may reasonably disagree on weight."],
        tool_run_ids=[t for t in [tool_run_id] if isinstance(t, str)],
    )
    state["weighing_record"] = weighing_record
    state["sequence"] = sequence + 1
    state.setdefault("move_event_ids", []).append(move_id)
    return state


def node_negotiation_and_alteration(state: GrammarState) -> GrammarState:
    framing_obj = state.get("framing") if isinstance(state.get("framing"), dict) else {}
    ledger_entries = state.get("ledger_entries") if isinstance(state.get("ledger_entries"), list) else []
    weighing_record = state.get("weighing_record") if isinstance(state.get("weighing_record"), dict) else {}
    context_pack = _build_context_pack(state, "negotiation_and_alteration", state.get("issues") or [], framing_obj)
    refs = _collect_context_pack_refs(context_pack)

    prompt = (
        "You are the Negotiator agent for The Planner's Assistant.\n"
        "Propose alterations/mitigations that could improve the balance.\n"
        "Return ONLY valid JSON: {\"negotiation_moves\": [...]}.\n"
        "Each move: {\"proposed_alterations\": [string...], \"addressed_considerations\": [entry_id...], \"validation_evidence_needed\": [string...] }.\n"
        "Do not include markdown fences."
    )
    negotiation_json, tool_run_id, errs = _llm_structured_sync(
        prompt_id="orchestrator.negotiation_and_alteration",
        prompt_version=1,
        prompt_name="Negotiation & alteration (grammar)",
        purpose="Generate plausible alterations/mitigations with evidence needs.",
        system_template=prompt,
        user_payload={
            "framing": framing_obj,
            "weighing_record": weighing_record,
            "ledger_entries": [{"entry_id": le.get("entry_id"), "statement": le.get("statement")} for le in ledger_entries],
            "context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None,
            "context_pack": context_pack.get("slices") if isinstance(context_pack, dict) else {},
        },
        output_schema_ref="schemas/NegotiationMove.schema.json",
    )
    negotiation_moves: list[dict[str, Any]] = []
    neg_raw = negotiation_json.get("negotiation_moves") if isinstance(negotiation_json, dict) else None
    if isinstance(neg_raw, list):
        for m in neg_raw:
            if not isinstance(m, dict):
                continue
            alterations = m.get("proposed_alterations")
            addressed = m.get("addressed_considerations")
            if not isinstance(alterations, list) or not all(isinstance(x, str) for x in alterations):
                continue
            addressed_ids = [x for x in addressed if isinstance(x, str)] if isinstance(addressed, list) else []
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

    sequence = int(state.get("sequence") or 1)
    move_id = _insert_move_event(
        run_id=state["run_id"],
        move_type="negotiation_and_alteration",
        sequence=sequence,
        status="success" if not errs else "partial",
        inputs={"context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None},
        outputs={"negotiation_moves": negotiation_moves},
        evidence_refs_considered=refs,
        assumptions_introduced=[],
        uncertainty_remaining=["Negotiation moves are proposals; viability requires evidence and political judgement."],
        tool_run_ids=[t for t in [tool_run_id] if isinstance(t, str)],
    )
    state["negotiation_moves"] = negotiation_moves
    state["sequence"] = sequence + 1
    state.setdefault("move_event_ids", []).append(move_id)
    return state


def node_positioning_and_narration(state: GrammarState) -> GrammarState:
    framing_obj = state.get("framing") if isinstance(state.get("framing"), dict) else {}
    weighing_record = state.get("weighing_record") if isinstance(state.get("weighing_record"), dict) else {}
    negotiation_moves = state.get("negotiation_moves") if isinstance(state.get("negotiation_moves"), list) else []
    context_pack = _build_context_pack(state, "positioning_and_narration", state.get("issues") or [], framing_obj)
    refs = _collect_context_pack_refs(context_pack)

    prompt = (
        "You are the Scribe agent for The Planner's Assistant.\n"
        "Write (1) a conditional position statement and (2) a concise planning balance narrative, both in UK planner tone.\n"
        "Return ONLY valid JSON: {\"position_statement\": string, \"planning_balance\": string, \"uncertainty_summary\": [string...] }.\n"
        "The position_statement must start with: \"Under framing ...\".\n"
        "Do not include markdown fences."
    )
    position_json, tool_run_id, errs = _llm_structured_sync(
        prompt_id="orchestrator.positioning_and_narration",
        prompt_version=1,
        prompt_name="Positioning & narration (grammar)",
        purpose="Produce a conditional position and narratable balance statement.",
        system_template=prompt,
        user_payload={
            "scenario": {"title": state.get("scenario_title") or "Scenario", "summary": state.get("scenario_summary") or ""},
            "framing": framing_obj,
            "weighing_record": weighing_record,
            "negotiation_moves": negotiation_moves,
            "context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None,
            "context_pack": context_pack.get("slices") if isinstance(context_pack, dict) else {},
        },
        output_schema_ref="schemas/Trajectory.schema.json",
    )

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
        position_statement = "Under framing, a reasonable position is provisional pending evidence."
    if not planning_balance:
        planning_balance = "Planning balance narrative is pending (LLM unavailable or failed)."

    trajectory_id = str(uuid4())
    evidence_atoms = state.get("evidence_atoms") if isinstance(state.get("evidence_atoms"), list) else []
    evidence_cards = _build_evidence_cards(evidence_atoms, limit=6)
    key_refs: list[str] = []
    for card in evidence_cards:
        refs = card.get("evidence_refs") if isinstance(card.get("evidence_refs"), list) else []
        for ref in refs:
            if isinstance(ref, str):
                key_refs.append(ref)
    if not key_refs:
        key_refs = refs[:20]
    sheet = {
        "title": f"{state.get('scenario_title') or 'Scenario'} × {framing_obj.get('frame_title') or 'Framing'}",
        "scenario": {"scenario_id": state.get("scenario_id"), "title": state.get("scenario_title") or "Scenario"},
        "framing": {
            "framing_id": framing_obj.get("frame_id"),
            "political_framing_id": state.get("political_framing_id"),
            "frame_title": framing_obj.get("frame_title"),
        },
        "sections": {
            "framing_summary": framing_obj.get("purpose") or "",
            "scenario_summary": state.get("scenario_summary") or "",
            "key_issues": [i.get("title") for i in (state.get("issues") or []) if isinstance(i, dict)][:12],
            "evidence_cards": evidence_cards,
            "planning_balance": planning_balance,
            "conditional_position": position_statement,
            "uncertainty_summary": uncertainty_summary,
        },
    }
    trajectory_obj = {
        "trajectory_id": trajectory_id,
        "scenario_id": state.get("scenario_id"),
        "framing_id": framing_obj.get("frame_id"),
        "position_statement": position_statement,
        "explicit_assumptions": [],
        "key_evidence_refs": key_refs[:20],
        "judgement_sheet_data": sheet,
    }

    sequence = int(state.get("sequence") or 1)
    move_id = _insert_move_event(
        run_id=state["run_id"],
        move_type="positioning_and_narration",
        sequence=sequence,
        status="success" if not errs else "partial",
        inputs={"context_pack_id": context_pack.get("context_pack_id") if isinstance(context_pack, dict) else None},
        outputs={"trajectory": trajectory_obj, "scenario_judgement_sheet": sheet},
        evidence_refs_considered=refs,
        assumptions_introduced=[],
        uncertainty_remaining=uncertainty_summary or ["Uncertainty remains; see evidence limitations and missing instruments."],
        tool_run_ids=[t for t in [tool_run_id] if isinstance(t, str)],
    )
    state["trajectory"] = trajectory_obj
    state["sequence"] = sequence + 1
    state.setdefault("move_event_ids", []).append(move_id)
    return state


def build_grammar_graph() -> StateGraph:
    graph = StateGraph(GrammarState)
    graph.add_node("framing", node_framing)
    graph.add_node("issue_surfacing", node_issue_surfacing)
    graph.add_node("evidence_curation", node_evidence_curation)
    graph.add_node("evidence_interpretation", node_evidence_interpretation)
    graph.add_node("considerations_formation", node_considerations_formation)
    graph.add_node("weighing_and_balance", node_weighing_and_balance)
    graph.add_node("negotiation_and_alteration", node_negotiation_and_alteration)
    graph.add_node("positioning_and_narration", node_positioning_and_narration)

    graph.add_edge("framing", "issue_surfacing")
    graph.add_edge("issue_surfacing", "evidence_curation")
    graph.add_edge("evidence_curation", "evidence_interpretation")
    graph.add_edge("evidence_interpretation", "considerations_formation")
    graph.add_edge("considerations_formation", "weighing_and_balance")
    graph.add_edge("weighing_and_balance", "negotiation_and_alteration")
    graph.add_edge("negotiation_and_alteration", "positioning_and_narration")
    graph.add_edge("positioning_and_narration", END)
    return graph


def run_grammar_graph(initial_state: GrammarState) -> GrammarState:
    graph = build_grammar_graph()
    compiled = graph.compile()
    return compiled.invoke(initial_state)
