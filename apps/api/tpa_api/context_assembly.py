from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .spatial_fingerprint import compute_site_fingerprint_sync, extract_site_ids_from_state_vector
from .spec_io import _read_yaml, _spec_root


MoveType = str


@dataclass(frozen=True)
class ContextAssemblyDeps:
    db_fetch_one: Callable[[str, tuple[Any, ...] | list[Any] | None], dict[str, Any] | None]
    db_fetch_all: Callable[[str, tuple[Any, ...] | list[Any] | None], list[dict[str, Any]]]
    db_execute: Callable[[str, tuple[Any, ...] | list[Any] | None], None]
    llm_structured_sync: Callable[..., tuple[dict[str, Any] | None, str | None, list[str]]]
    retrieve_chunks_hybrid_sync: Callable[..., dict[str, Any]]
    retrieve_policy_clauses_hybrid_sync: Callable[..., dict[str, Any]]
    utc_now_iso: Callable[[], str]
    utc_now: Callable[[], Any]


def _clamp_int(value: int, *, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except Exception:
        v = lo
    return max(lo, min(v, hi))


def _safe_list_of_str(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in value:
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
        if len(out) >= limit:
            break
    return out


def _safe_issue_id(issue: dict[str, Any]) -> str | None:
    iid = issue.get("issue_id")
    return iid if isinstance(iid, str) and iid else None


def _extract_frame_payload(obj: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    if isinstance(obj.get("retrieval_frame"), dict):
        return obj["retrieval_frame"]
    return obj


_CONTEXT_PACK_TEMPLATES_CACHE: tuple[float, dict[str, Any]] | None = None


def _load_context_pack_templates() -> dict[str, Any]:
    """
    Loads planner-editable Context Pack Templates from the spec pack.

    Best-effort: returns an empty structure if missing/unreadable.
    """
    global _CONTEXT_PACK_TEMPLATES_CACHE  # noqa: PLW0603

    try:
        path = (_spec_root() / "capabilities" / "CONTEXT_PACK_TEMPLATES.yaml").resolve()
        mtime = path.stat().st_mtime
    except Exception:  # noqa: BLE001
        return {"templates": [], "defaults": {}}

    if _CONTEXT_PACK_TEMPLATES_CACHE and _CONTEXT_PACK_TEMPLATES_CACHE[0] == mtime:
        return _CONTEXT_PACK_TEMPLATES_CACHE[1]

    try:
        data = _read_yaml(Path(path))
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}
    _CONTEXT_PACK_TEMPLATES_CACHE = (mtime, data)
    return data


def _applicable_context_pack_templates(
    *,
    work_mode: str,
    culp_stage_id: str | None,
    move_type: MoveType,
) -> list[dict[str, Any]]:
    data = _load_context_pack_templates()
    templates = data.get("templates") if isinstance(data, dict) else None
    if not isinstance(templates, list):
        return []

    matches: list[dict[str, Any]] = []
    for t in templates:
        if not isinstance(t, dict):
            continue
        if t.get("mode") != work_mode:
            continue
        mt = t.get("move_type")
        if isinstance(mt, str):
            ok_mt = mt == move_type
        elif isinstance(mt, list):
            ok_mt = move_type in [x for x in mt if isinstance(x, str)]
        else:
            ok_mt = False
        if not ok_mt:
            continue

        stage = t.get("culp_stage_id")
        # stage is optional; null means "all stages".
        if stage is not None and culp_stage_id and stage != culp_stage_id:
            continue
        if stage is not None and not culp_stage_id and stage is not None:
            # caller has no stage; only apply stage-agnostic templates (stage=null).
            continue

        matches.append(t)

    # Apply stage-specific templates first (more specific), then stage-agnostic.
    matches.sort(key=lambda x: 0 if x.get("culp_stage_id") is not None else 1)
    return matches


def _dedupe_queries(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str | None]] = set()
    out: list[dict[str, Any]] = []
    for q in queries:
        if not isinstance(q, dict):
            continue
        query_text = q.get("query") if isinstance(q.get("query"), str) else ""
        modality = q.get("modality") if isinstance(q.get("modality"), str) else "text"
        purpose = q.get("purpose") if isinstance(q.get("purpose"), str) else "primary"
        issue_id = q.get("issue_id") if isinstance(q.get("issue_id"), str) else None
        key = (query_text.strip().lower(), modality, issue_id)
        if not key[0]:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def _trim_text(text: str, *, max_chars: int) -> str:
    if not isinstance(text, str):
        return ""
    t = text.strip()
    if len(t) <= max_chars:
        return t
    return t[:max_chars].rstrip() + "…"


def build_or_refine_retrieval_frame_sync(
    *,
    deps: ContextAssemblyDeps,
    run_id: str,
    move_type: MoveType,
    work_mode: str | None,
    culp_stage_id: str | None,
    authority_id: str,
    plan_cycle_id: str | None,
    scenario: dict[str, Any],
    framing: dict[str, Any],
    issues: list[dict[str, Any]],
    token_budget: int | None,
    time_budget_seconds: float,
    max_candidates_per_query: int,
    max_atoms_per_issue: int,
) -> dict[str, Any]:
    """
    Creates a persisted RetrievalFrame row for the run+move_type.

    If a current frame exists, it is superseded and a new version is created. This supports explicit refinement /
    backtracking without pretending the grammar is linear.
    """
    try:
        previous = deps.db_fetch_one(
            """
            SELECT id, version, frame_jsonb
            FROM retrieval_frames
            WHERE run_id = %s::uuid AND move_type = %s AND is_current = true
            LIMIT 1
            """,
            (run_id, move_type),
        )
    except Exception:  # noqa: BLE001
        previous = None
    based_on_id = str(previous["id"]) if previous and previous.get("id") else None
    prev_version = int(previous.get("version") or 0) if previous else 0
    version = prev_version + 1
    previous_frame = previous.get("frame_jsonb") if isinstance(previous, dict) else None

    budgets = {
        "token_budget": int(token_budget) if isinstance(token_budget, int) else None,
        "time_budget_seconds": float(time_budget_seconds),
        "max_candidates_per_query": int(max_candidates_per_query),
        "max_atoms_per_issue": int(max_atoms_per_issue),
    }

    work_mode_clean = work_mode if isinstance(work_mode, str) and work_mode.strip() else "plan_studio"

    applicable_templates = _applicable_context_pack_templates(
        work_mode=work_mode_clean,
        culp_stage_id=culp_stage_id if isinstance(culp_stage_id, str) and culp_stage_id else None,
        move_type=move_type,
    )
    defaults = _load_context_pack_templates().get("defaults") if isinstance(_load_context_pack_templates(), dict) else {}
    max_global_queries = defaults.get("max_global_queries_per_template")
    max_global_queries = int(max_global_queries) if isinstance(max_global_queries, int) else 8
    max_global_queries = _clamp_int(max_global_queries, lo=0, hi=30)
    max_instrument_hints = defaults.get("max_instrument_hints_per_template")
    max_instrument_hints = int(max_instrument_hints) if isinstance(max_instrument_hints, int) else 6
    max_instrument_hints = _clamp_int(max_instrument_hints, lo=0, hi=30)

    template_global_queries: list[dict[str, Any]] = []
    template_instrument_hints: list[dict[str, Any]] = []
    applied_template_ids: list[str] = []
    for t in applicable_templates[:10]:
        tid = t.get("template_id") if isinstance(t.get("template_id"), str) else None
        if tid:
            applied_template_ids.append(tid)
        gq = t.get("global_queries")
        if isinstance(gq, list):
            for q in gq[:max_global_queries]:
                if not isinstance(q, dict):
                    continue
                qtext = q.get("query")
                if not isinstance(qtext, str) or not qtext.strip():
                    continue
                purpose = q.get("purpose") if isinstance(q.get("purpose"), str) else "contextual"
                modality = q.get("modality") if isinstance(q.get("modality"), str) else "text"
                if purpose not in {"primary", "countervailing", "contextual"}:
                    purpose = "contextual"
                if modality not in {"text", "spatial", "visual", "instrument", "precedent", "consultation"}:
                    modality = "text"
                template_global_queries.append(
                    {
                        "issue_id": None,
                        "purpose": purpose,
                        "modality": modality,
                        "query": qtext.strip()[:300],
                        "filters": {},
                        "top_k": None,
                    }
                )
        hints = t.get("instrument_hints")
        if isinstance(hints, list):
            for h in hints[:max_instrument_hints]:
                if not isinstance(h, dict):
                    continue
                instrument_id = h.get("instrument_id")
                if not isinstance(instrument_id, str) or not instrument_id.strip():
                    continue
                template_instrument_hints.append(
                    {
                        "instrument_id": instrument_id.strip(),
                        "purpose": h.get("purpose") if isinstance(h.get("purpose"), str) else "",
                        "when_issue_keywords": _safe_list_of_str(h.get("when_issue_keywords"), limit=12),
                        "blocking": bool(h.get("blocking")) if h.get("blocking") is not None else False,
                    }
                )

    sys = (
        "You are the Scout agent for The Planner's Assistant.\n"
        "Build a RetrievalFrame for Context Assembly.\n"
        "A RetrievalFrame is a logged plan for what evidence to seek for the next step; it is NOT a conclusion.\n"
        "Return ONLY valid JSON.\n"
        "Output shape MUST be compatible with schemas/RetrievalFrame.schema.json.\n"
        "Rules:\n"
        "- Keep queries short and specific.\n"
        "- Include at least one text query per issue (purpose=primary).\n"
        "- Where plausible, include a text query intended to surface countervailing evidence (purpose=countervailing).\n"
        "- If you request spatial/visual modalities, still include text queries.\n"
        "- Do not invent IDs; issue_id must match the provided issues.\n"
    )
    user_payload = {
        "run_id": run_id,
        "work_mode": work_mode_clean,
        "culp_stage_id": culp_stage_id,
        "move_type": move_type,
        "authority_id": authority_id,
        "plan_cycle_id": plan_cycle_id,
        "scenario": scenario,
        "political_framing": framing,
        "issues": [{"issue_id": _safe_issue_id(i), "title": i.get("title"), "why_material": i.get("why_material")} for i in issues],
        "budgets": budgets,
        "previous_retrieval_frame": previous_frame if isinstance(previous_frame, dict) else None,
        "context_pack_template_ids": applied_template_ids,
        "template_global_query_intents": template_global_queries[:max_global_queries],
        "template_instrument_hints": template_instrument_hints[:max_instrument_hints],
    }

    obj, llm_tool_run_id, errs = deps.llm_structured_sync(
        prompt_id="context_assembly.build_retrieval_frame",
        prompt_version=1,
        prompt_name="Context Assembly: build RetrievalFrame",
        purpose="Plan move-specific retrieval (queries, modalities, budgets) without deciding conclusions.",
        system_template=sys,
        user_payload=user_payload,
        time_budget_seconds=min(90.0, max(10.0, time_budget_seconds)),
        temperature=0.5,
        max_tokens=1400,
        output_schema_ref="schemas/RetrievalFrame.schema.json",
    )

    fallback_mode = False
    frame_payload = _extract_frame_payload(obj)

    if not isinstance(frame_payload, dict) or not isinstance(frame_payload.get("queries"), list):
        fallback_mode = True
        frame_payload = {
            "move_type": move_type,
            "modalities": ["text"],
            "queries": [],
            "budgets": budgets,
            "notes": "Fallback retrieval frame (LLM unavailable or invalid output).",
            "assumptions": ["Fallback: queries use issue titles directly."],
            "uncertainty": ["RetrievalFrame generation failed; evidence coverage may be poor."],
        }

    # Normalize queries and enforce basic constraints.
    allowed_issue_ids = {iid for iid in (_safe_issue_id(i) for i in issues) if iid}
    issue_title_by_id: dict[str, str] = {}
    for issue in issues:
        iid = _safe_issue_id(issue)
        if not iid:
            continue
        title = issue.get("title")
        if isinstance(title, str) and title.strip():
            issue_title_by_id[iid] = title.strip()
    queries_in = frame_payload.get("queries")
    queries: list[dict[str, Any]] = []
    if isinstance(queries_in, list):
        for q in queries_in[:200]:
            if not isinstance(q, dict):
                continue
            query_text = q.get("query")
            if not isinstance(query_text, str) or not query_text.strip():
                continue
            modality = q.get("modality") if isinstance(q.get("modality"), str) else "text"
            purpose = q.get("purpose") if isinstance(q.get("purpose"), str) else "primary"
            issue_id = q.get("issue_id")
            if issue_id is not None and (not isinstance(issue_id, str) or issue_id not in allowed_issue_ids):
                issue_id = None
            if modality not in {"text", "spatial", "visual", "instrument", "precedent", "consultation"}:
                modality = "text"
            if purpose not in {"primary", "countervailing", "contextual"}:
                purpose = "primary"
            top_k = q.get("top_k")
            top_k_clean = int(top_k) if isinstance(top_k, int) else None
            queries.append(
                {
                    "issue_id": issue_id,
                    "purpose": purpose,
                    "modality": modality,
                    "query": query_text.strip()[:300],
                    "filters": q.get("filters") if isinstance(q.get("filters"), dict) else {},
                    "top_k": top_k_clean,
                }
            )

    if not queries:
        # Always ensure at least one query per issue to avoid empty frames.
        for issue in issues[:12]:
            title = issue.get("title") if isinstance(issue.get("title"), str) else "planning issue"
            iid = _safe_issue_id(issue)
            queries.append({"issue_id": iid, "purpose": "primary", "modality": "text", "query": title[:300], "filters": {}, "top_k": None})

    # Apply global query boosters from templates (planner-editable coverage heuristics).
    queries.extend(template_global_queries)
    queries = _dedupe_queries(queries)

    # Planner heuristics: ensure each issue has (a) a primary text query and (b) a countervailing text query.
    # Countervailing is normative (selected later by the LLM), but we must supply plausible candidates to choose from.
    for issue in issues[:20]:
        iid = _safe_issue_id(issue)
        if not iid or iid not in allowed_issue_ids:
            continue
        has_primary = any(
            isinstance(q, dict)
            and q.get("issue_id") == iid
            and q.get("modality") == "text"
            and q.get("purpose") == "primary"
            for q in queries
        )
        if not has_primary:
            title = issue_title_by_id.get(iid) or "planning issue"
            queries.append({"issue_id": iid, "purpose": "primary", "modality": "text", "query": title[:300], "filters": {}, "top_k": None})

        has_countervailing = any(
            isinstance(q, dict)
            and q.get("issue_id") == iid
            and q.get("modality") == "text"
            and q.get("purpose") == "countervailing"
            for q in queries
        )
        if not has_countervailing:
            title = issue_title_by_id.get(iid) or "planning issue"
            counter_query = f"{title} harm constraint adverse impact mitigation exception"
            queries.append(
                {
                    "issue_id": iid,
                    "purpose": "countervailing",
                    "modality": "text",
                    "query": counter_query[:300],
                    "filters": {},
                    "top_k": None,
                }
            )

    modalities = frame_payload.get("modalities")
    if not isinstance(modalities, list):
        modalities = ["text"]
    modalities = [m for m in modalities if isinstance(m, str) and m in {"text", "spatial", "visual", "instrument", "precedent", "consultation"}]
    if "text" not in modalities:
        modalities = ["text", *modalities]

    assumptions = _safe_list_of_str(frame_payload.get("assumptions"), limit=12)
    uncertainty = _safe_list_of_str(frame_payload.get("uncertainty"), limit=12)

    # Multimodal-first defaults (so spatial/visual are considered even if the RetrievalFrame LLM is conservative).
    has_spatial_query = any(isinstance(q, dict) and q.get("modality") == "spatial" for q in queries)
    site_ids = extract_site_ids_from_state_vector(scenario.get("state_vector") if isinstance(scenario, dict) else {})
    if site_ids and not has_spatial_query:
        queries.append(
            {
                "issue_id": None,
                "purpose": "contextual",
                "modality": "spatial",
                "query": "Site fingerprint and constraint intersections",
                "filters": {},
                "top_k": None,
            }
        )
        if "spatial" not in modalities:
            modalities.append("spatial")
        assumptions = (assumptions + ["Defaulted to include spatial fingerprint evidence because the scenario contains site ids."])[:12]

    has_visual_query = any(isinstance(q, dict) and q.get("modality") == "visual" for q in queries)
    if not has_visual_query:
        has_visual_assets = False
        try:
            has_visual_assets = deps.db_fetch_one(
                """
                SELECT 1
                FROM visual_assets va
                JOIN documents d ON d.id = va.document_id
                WHERE d.authority_id = %s
                  AND (%s::uuid IS NULL OR d.plan_cycle_id = %s::uuid)
                  AND d.is_active = true
                LIMIT 1
                """,
                (authority_id, plan_cycle_id, plan_cycle_id),
            ) is not None
        except Exception:  # noqa: BLE001
            has_visual_assets = False
        if has_visual_assets:
            queries.append(
                {
                    "issue_id": None,
                    "purpose": "contextual",
                    "modality": "visual",
                    "query": "Relevant plans, maps, photos, and other visuals",
                    "filters": {},
                    "top_k": None,
                }
            )
            if "visual" not in modalities:
                modalities.append("visual")
            assumptions = (assumptions + ["Defaulted to include visual evidence because VisualAssets exist for this authority/plan cycle."])[:12]

    retrieval_frame_id = str(uuid4())
    now = deps.utc_now()
    frame_out = {
        "retrieval_frame_id": retrieval_frame_id,
        "run_id": run_id,
        "move_type": move_type,
        "work_mode": work_mode_clean,
        "culp_stage_id": culp_stage_id,
        "version": version,
        "based_on_retrieval_frame_id": based_on_id,
        "budgets": budgets,
        "modalities": modalities,
        "queries": queries,
        "applied_context_pack_template_ids": applied_template_ids,
        "instrument_hints": template_instrument_hints[:max_instrument_hints],
        "deliberate_omissions_policy": frame_payload.get("deliberate_omissions_policy")
        if isinstance(frame_payload.get("deliberate_omissions_policy"), str)
        else "Record omissions explicitly (duplicates/out-of-scope/insufficient provenance).",
        "notes": frame_payload.get("notes") if isinstance(frame_payload.get("notes"), str) else None,
        "assumptions": assumptions,
        "uncertainty": uncertainty,
        "created_at": deps.utc_now_iso(),
        "tool_run_id": llm_tool_run_id,
        "fallback_mode": fallback_mode,
        "errors": errs[:10] if isinstance(errs, list) else [],
    }

    # Persist (best effort). If the table isn't present yet, skip without failing the run.
    try:
        if based_on_id:
            deps.db_execute(
                """
                UPDATE retrieval_frames
                SET is_current = false, superseded_by_frame_id = %s::uuid
                WHERE id = %s::uuid
                """,
                (retrieval_frame_id, based_on_id),
            )
        deps.db_execute(
            """
            INSERT INTO retrieval_frames (id, run_id, move_type, version, is_current, superseded_by_frame_id, tool_run_id, frame_jsonb, created_at)
            VALUES (%s, %s::uuid, %s, %s, true, NULL, %s::uuid, %s::jsonb, %s)
            """,
            (
                retrieval_frame_id,
                run_id,
                move_type,
                version,
                llm_tool_run_id,
                json.dumps(frame_out, ensure_ascii=False),
                now,
            ),
        )
    except Exception:  # noqa: BLE001
        pass

    return frame_out


def assemble_curated_evidence_set_sync(
    *,
    deps: ContextAssemblyDeps,
    run_id: str,
    work_mode: str | None = None,
    culp_stage_id: str | None = None,
    authority_id: str,
    plan_cycle_id: str | None,
    scenario: dict[str, Any],
    framing: dict[str, Any],
    issues: list[dict[str, Any]],
    evidence_per_issue: int,
    token_budget: int | None,
    time_budget_seconds: float,
) -> dict[str, Any]:
    """
    Context Assembly v1: hybrid candidate generation (text) + LLM-logged selection, producing a Move 3 CuratedEvidenceSet.

    Includes first-cut multimodal candidate generation:
    - text: hybrid retrieval + reranking
    - spatial: deterministic site fingerprint tool (Slice C)
    - visual: VisualAsset candidates (Slice I scaffolding)
    """
    evidence_per_issue = _clamp_int(evidence_per_issue, lo=1, hi=10)
    max_candidates_per_query = max(10, min(40, evidence_per_issue * 8))
    max_atoms_per_issue = max(2, min(12, evidence_per_issue * 3))

    retrieval_frame = build_or_refine_retrieval_frame_sync(
        deps=deps,
        run_id=run_id,
        move_type="evidence_curation",
        work_mode=work_mode,
        culp_stage_id=culp_stage_id,
        authority_id=authority_id,
        plan_cycle_id=plan_cycle_id,
        scenario=scenario,
        framing=framing,
        issues=issues,
        token_budget=token_budget,
        time_budget_seconds=time_budget_seconds,
        max_candidates_per_query=max_candidates_per_query,
        max_atoms_per_issue=max_atoms_per_issue,
    )

    # --- Candidate generation (multimodal)
    candidate_by_ref: dict[str, dict[str, Any]] = {}
    candidates_by_issue: dict[str, list[str]] = {}
    tool_run_ids: list[str] = []
    computed_site_tool_run_by_site_id: dict[str, str] = {}
    computed_site_fingerprint_by_site_id: dict[str, dict[str, Any]] = {}
    loaded_visual_assets: list[dict[str, Any]] | None = None
    issue_ids_all = [iid for iid in (_safe_issue_id(i) for i in issues) if iid]

    def add_candidate(*, issue_id: str, candidate: dict[str, Any]) -> None:
        ev = candidate.get("evidence_ref")
        if not isinstance(ev, str) or "::" not in ev:
            return
        candidate_by_ref.setdefault(ev, candidate)
        candidates_by_issue.setdefault(issue_id, [])
        if ev not in candidates_by_issue[issue_id]:
            candidates_by_issue[issue_id].append(ev)

    # Non-linear refinement support: include already-executed ToolRequests (instrument outputs) as candidates.
    # This helps a planner re-run Move 3 after tool execution without losing provenance.
    try:
        prior_tools = deps.db_fetch_all(
            """
            SELECT
              tr.id AS tool_request_id,
              tr.tool_name,
              tr.instrument_id,
              tr.purpose,
              tr.status,
              tr.tool_run_id,
              tr.outputs_jsonb,
              tr.evidence_refs_jsonb,
              tr.completed_at,
              t.confidence_hint AS tool_confidence_hint,
              t.uncertainty_note AS tool_uncertainty_note
            FROM tool_requests tr
            LEFT JOIN tool_runs t ON t.id = tr.tool_run_id
            WHERE tr.run_id = %s::uuid
              AND tr.tool_run_id IS NOT NULL
              AND tr.status IN ('success', 'partial')
            ORDER BY tr.completed_at DESC NULLS LAST, tr.created_at DESC
            LIMIT 60
            """,
            (run_id,),
        )
    except Exception:  # noqa: BLE001
        prior_tools = []

    for r in prior_tools[:60]:
        if not isinstance(r, dict):
            continue
        tool_run_id = r.get("tool_run_id")
        if tool_run_id is None:
            continue
        tool_run_id = str(tool_run_id)
        instrument_id = r.get("instrument_id") if isinstance(r.get("instrument_id"), str) else ""
        tool_name = r.get("tool_name") if isinstance(r.get("tool_name"), str) else "request_instrument"
        purpose_text = r.get("purpose") if isinstance(r.get("purpose"), str) else ""
        outputs = r.get("outputs_jsonb") if isinstance(r.get("outputs_jsonb"), dict) else {}
        evidence_refs_logged = r.get("evidence_refs_jsonb") if isinstance(r.get("evidence_refs_jsonb"), list) else []

        # Prefer the evidence ref recorded by the tool request, otherwise fall back to a stable tool_run ref.
        evidence_ref = None
        for ev in evidence_refs_logged:
            if isinstance(ev, str) and ev.startswith(f"tool_run::{tool_run_id}::"):
                evidence_ref = ev
                break
        if not evidence_ref:
            evidence_ref = f"tool_run::{tool_run_id}::instrument_output"

        title_bits = [instrument_id or tool_name, purpose_text.strip() or None]
        title = " · ".join([b for b in title_bits if isinstance(b, str) and b.strip()]) or "Instrument output"
        summary = outputs.get("summary") if isinstance(outputs.get("summary"), str) else ""
        if not summary:
            summary = _trim_text(json.dumps(outputs, ensure_ascii=False), max_chars=700)

        limitations = r.get("tool_uncertainty_note") if isinstance(r.get("tool_uncertainty_note"), str) else ""
        if not limitations.strip():
            limitations = "Instrument output is non-deterministic or data-dependent; verify limitations and provenance."

        for iid in issue_ids_all:
            add_candidate(
                issue_id=iid,
                candidate={
                    "candidate_type": "instrument_output",
                    "query_purpose": "contextual",
                    "query": "Previously executed tool requests",
                    "tool_request_id": str(r.get("tool_request_id") or ""),
                    "tool_run_id": tool_run_id,
                    "tool_name": tool_name,
                    "instrument_id": instrument_id,
                    "title": title,
                    "summary": summary,
                    "limitations_text": limitations,
                    "outputs": outputs,
                    "confidence_hint": r.get("tool_confidence_hint"),
                    "evidence_ref": evidence_ref,
                    "scores": {"modality": "instrument"},
                },
            )

    # Run queries from the frame. If issue_id is missing, attach to all issues.
    for q in retrieval_frame.get("queries") if isinstance(retrieval_frame.get("queries"), list) else []:
        if not isinstance(q, dict):
            continue
        modality = q.get("modality") if isinstance(q.get("modality"), str) else "text"
        purpose = q.get("purpose") if isinstance(q.get("purpose"), str) else "primary"
        top_k = q.get("top_k")
        limit = int(top_k) if isinstance(top_k, int) else max_candidates_per_query
        limit = _clamp_int(limit, lo=5, hi=50)
        target_issue_ids: list[str]
        issue_id = q.get("issue_id")
        if isinstance(issue_id, str) and issue_id:
            target_issue_ids = [issue_id]
        else:
            target_issue_ids = [iid for iid in (_safe_issue_id(i) for i in issues) if iid]

        query_text = q.get("query")
        query_text = query_text.strip() if isinstance(query_text, str) else ""

        if modality == "spatial":
            site_ids = extract_site_ids_from_state_vector(scenario.get("state_vector") if isinstance(scenario, dict) else {})
            for site_id in site_ids[:10]:
                if site_id in computed_site_tool_run_by_site_id:
                    tool_run_id = computed_site_tool_run_by_site_id[site_id]
                    fingerprint = computed_site_fingerprint_by_site_id.get(site_id) or {}
                else:
                    fingerprint, tool_run_id, _errs = compute_site_fingerprint_sync(
                        db_fetch_one=deps.db_fetch_one,
                        db_fetch_all=deps.db_fetch_all,
                        db_execute=deps.db_execute,
                        utc_now=deps.utc_now,
                        site_id=site_id,
                        authority_id=authority_id,
                        plan_cycle_id=plan_cycle_id,
                        limit_features=120,
                    )
                    computed_site_tool_run_by_site_id[site_id] = tool_run_id
                    computed_site_fingerprint_by_site_id[site_id] = fingerprint or {}

                tool_run_ids.append(tool_run_id)
                evidence_ref = f"tool_run::{tool_run_id}::site_fingerprint"
                summary = fingerprint.get("summary") if isinstance(fingerprint, dict) else None
                limitations_text = fingerprint.get("limitations_text") if isinstance(fingerprint, dict) else None

                for iid in target_issue_ids:
                    add_candidate(
                        issue_id=iid,
                        candidate={
                            "candidate_type": "site_fingerprint",
                            "query_purpose": purpose,
                            "query": query_text,
                            "site_id": site_id,
                            "tool_run_id": tool_run_id,
                            "summary": summary or "Site fingerprint computed (see tool run output).",
                            "limitations_text": limitations_text
                            or "Deterministic spatial fingerprint; verify constraint layer completeness and plan-cycle applicability.",
                            "fingerprint": fingerprint or {},
                            "evidence_ref": evidence_ref,
                            "scores": {"modality": "spatial"},
                        },
                    )

                # Also surface a bounded, explicit list of intersecting spatial features as candidates.
                intersections = fingerprint.get("intersections") if isinstance(fingerprint, dict) else None
                if isinstance(intersections, list) and intersections:
                    by_type: dict[str, list[dict[str, Any]]] = {}
                    for it in intersections[:400]:
                        if not isinstance(it, dict):
                            continue
                        fid = it.get("spatial_feature_id")
                        if not isinstance(fid, str) or not fid:
                            continue
                        ftype = it.get("type") if isinstance(it.get("type"), str) and it.get("type") else "unknown"
                        by_type.setdefault(ftype, []).append(it)

                    selected_features: list[dict[str, Any]] = []
                    for ftype, items in sorted(by_type.items(), key=lambda x: (-len(x[1]), x[0]))[:12]:
                        for it in items[:3]:
                            selected_features.append(it)
                            if len(selected_features) >= 24:
                                break
                        if len(selected_features) >= 24:
                            break

                    for it in selected_features:
                        fid = it.get("spatial_feature_id")
                        if not isinstance(fid, str) or not fid:
                            continue
                        ftype = it.get("type") if isinstance(it.get("type"), str) and it.get("type") else "unknown"
                        props = it.get("properties") if isinstance(it.get("properties"), dict) else {}
                        label = (
                            props.get("name")
                            or props.get("title")
                            or props.get("label")
                            or props.get("ref")
                            or props.get("code")
                        )
                        label = str(label) if label is not None and str(label).strip() else fid[:8]
                        title = f"{ftype} · {label}"
                        summary = props.get("description") if isinstance(props.get("description"), str) else ""
                        if not summary:
                            summary = _trim_text(json.dumps(props, ensure_ascii=False), max_chars=700) if props else ""
                        evidence_ref = f"spatial_feature::{fid}::properties"
                        for iid in target_issue_ids:
                            add_candidate(
                                issue_id=iid,
                                candidate={
                                    "candidate_type": "spatial_feature",
                                    "query_purpose": purpose,
                                    "query": query_text,
                                    "site_id": site_id,
                                    "spatial_feature_id": fid,
                                    "feature_type": ftype,
                                    "spatial_scope": it.get("spatial_scope"),
                                    "properties": props,
                                    "title": title,
                                    "summary": summary,
                                    "limitations_text": (
                                        "Deterministic constraint record from the canonical spatial_features table; "
                                        "verify layer completeness, temporal validity, and plan-cycle applicability."
                                    ),
                                    "evidence_ref": evidence_ref,
                                    "scores": {"modality": "spatial", "feature_type": ftype},
                                },
                            )
            continue

        if modality == "visual":
            if loaded_visual_assets is None:
                try:
                    loaded_visual_assets = deps.db_fetch_all(
                        """
                        SELECT
                          va.id AS visual_asset_id,
                          va.asset_type,
                          va.page_number,
                          va.blob_path,
                          va.metadata AS asset_metadata,
                          d.id AS document_id,
                          d.metadata->>'title' AS document_title
                        FROM visual_assets va
                        JOIN documents d ON d.id = va.document_id
                        WHERE d.authority_id = %s
                          AND (%s::uuid IS NULL OR d.plan_cycle_id = %s::uuid)
                          AND d.is_active = true
                        ORDER BY d.metadata->>'title' ASC NULLS LAST, va.page_number ASC NULLS LAST
                        LIMIT %s
                        """,
                        (authority_id, plan_cycle_id, plan_cycle_id, max_candidates_per_query),
                    )
                except Exception:  # noqa: BLE001
                    loaded_visual_assets = []

            for r in (loaded_visual_assets or [])[:limit]:
                if not isinstance(r, dict):
                    continue
                vid = r.get("visual_asset_id")
                if not isinstance(vid, str):
                    continue
                evidence_ref = f"visual_asset::{vid}::blob"
                title_bits = [
                    r.get("document_title") or "Document",
                    f"p{r.get('page_number')}" if r.get("page_number") else None,
                    r.get("asset_type") or "visual",
                ]
                title = " · ".join([b for b in title_bits if isinstance(b, str) and b.strip()])
                for iid in target_issue_ids:
                    add_candidate(
                        issue_id=iid,
                        candidate={
                            "candidate_type": "visual_asset",
                            "query_purpose": purpose,
                            "query": query_text,
                            "visual_asset_id": vid,
                            "asset_type": r.get("asset_type"),
                            "page_number": r.get("page_number"),
                            "document_id": r.get("document_id"),
                            "document_title": r.get("document_title"),
                            "blob_path": r.get("blob_path"),
                            "asset_metadata": r.get("asset_metadata") if isinstance(r.get("asset_metadata"), dict) else {},
                            "title": title,
                            "evidence_ref": evidence_ref,
                            "scores": {"modality": "visual"},
                        },
                    )
            continue

        if modality != "text":
            continue

        if not query_text:
            continue

        clause = deps.retrieve_policy_clauses_hybrid_sync(
            query=query_text,
            authority_id=authority_id,
            plan_cycle_id=plan_cycle_id,
            limit=max(6, min(30, limit // 2)),
            rerank=True,
            rerank_top_n=max(10, min(50, limit)),
        )
        for tid in [clause.get("tool_run_id"), clause.get("rerank_tool_run_id")]:
            if isinstance(tid, str):
                tool_run_ids.append(tid)

        chunk = deps.retrieve_chunks_hybrid_sync(
            query=query_text,
            authority_id=authority_id,
            plan_cycle_id=plan_cycle_id,
            limit=limit,
            rerank=True,
            rerank_top_n=max(10, min(50, limit)),
        )
        for tid in [chunk.get("tool_run_id"), chunk.get("rerank_tool_run_id")]:
            if isinstance(tid, str):
                tool_run_ids.append(tid)

        clause_results = clause.get("results") if isinstance(clause, dict) else None
        if isinstance(clause_results, list):
            for r in clause_results[:limit]:
                if not isinstance(r, dict):
                    continue
                for iid in target_issue_ids:
                    add_candidate(
                        issue_id=iid,
                        candidate={
                            **r,
                            "candidate_type": "policy_clause",
                            "query_purpose": purpose,
                            "query": query_text,
                        },
                    )

        chunk_results = chunk.get("results") if isinstance(chunk, dict) else None
        if isinstance(chunk_results, list):
            for r in chunk_results[:limit]:
                if not isinstance(r, dict):
                    continue
                for iid in target_issue_ids:
                    add_candidate(
                        issue_id=iid,
                        candidate={
                            **r,
                            "candidate_type": "doc_chunk",
                            "query_purpose": purpose,
                            "query": query_text,
                        },
                    )

    # --- LLM selection (normatively judged counter-evidence)
    issue_briefs = []
    allowed_refs: set[str] = set()
    for issue in issues:
        iid = _safe_issue_id(issue)
        if not iid:
            continue
        refs = candidates_by_issue.get(iid, [])
        allowed_refs.update(refs)
        brief = {
            "issue_id": iid,
            "title": issue.get("title"),
            "why_material": issue.get("why_material"),
            "candidate_evidence": [],
        }
        for ev in refs[: max_candidates_per_query]:
            c = candidate_by_ref.get(ev) or {}
            brief["candidate_evidence"].append(
                {
                    "evidence_ref": ev,
                    "type": c.get("candidate_type"),
                    "title": c.get("title"),
                    "summary": c.get("summary"),
                    "site_id": c.get("site_id"),
                    "tool_run_id": c.get("tool_run_id"),
                    "instrument_id": c.get("instrument_id"),
                    "feature_type": c.get("feature_type"),
                    "spatial_scope": c.get("spatial_scope"),
                    "asset_type": c.get("asset_type"),
                    "policy_ref": c.get("policy_ref"),
                    "clause_ref": c.get("clause_ref"),
                    "document_title": c.get("document_title"),
                    "page_number": c.get("page_number"),
                    "section_path": c.get("section_path"),
                    "snippet": c.get("snippet"),
                    "query_purpose": c.get("query_purpose"),
                    "scores": c.get("scores"),
                }
            )
        issue_briefs.append(brief)

    sys = (
        "You are the Scout agent for The Planner's Assistant.\n"
        "Task: select evidence_refs into a CuratedEvidenceSet for Move 3 (Evidence curation).\n"
        "This is a normative, planner-shaped selection under the political framing: include countervailing evidence where available.\n"
        "Return ONLY valid JSON compatible with schemas/ContextAssemblySelection.schema.json.\n"
        "Rules:\n"
        "- You MUST only choose evidence_refs that appear in the provided candidate lists.\n"
        "- Candidate types may include: policy_clause, doc_chunk, site_fingerprint, spatial_feature, visual_asset, instrument_output.\n"
        "- For each issue:\n"
        "  - choose up to max_atoms_per_issue total (across supporting/countervailing/contextual)\n"
        "  - include at least 1 supporting item where possible\n"
        "  - include at least 1 countervailing item where plausible (not tokenistic)\n"
        "- If evidence is missing (e.g. spatial constraints, transport instruments, plan maps), emit ToolRequests.\n"
        "- If instrument_hints are provided, treat them as available evidence instruments and propose ToolRequests where they would close gaps.\n"
        "- If you select visual_asset evidence_refs and interpretation would benefit from a VLM instrument run, request instrument_id=\"townscape_vlm_assessment\" with inputs {\"visual_asset_refs\": [...], \"viewpoint_context\": {...}}.\n"
        "- Record deliberate omissions (e.g. duplicates, out-of-scope plan cycles, low provenance) explicitly.\n"
        "- Do not invent citations.\n"
    )
    selection_payload = {
        "run_id": run_id,
        "work_mode": retrieval_frame.get("work_mode"),
        "culp_stage_id": retrieval_frame.get("culp_stage_id"),
        "authority_id": authority_id,
        "plan_cycle_id": plan_cycle_id,
        "scenario": scenario,
        "political_framing": framing,
        "budgets": retrieval_frame.get("budgets"),
        "max_atoms_per_issue": max_atoms_per_issue,
        "issues": issue_briefs,
        "deliberate_omissions_policy": retrieval_frame.get("deliberate_omissions_policy"),
        "instrument_hints": retrieval_frame.get("instrument_hints") if isinstance(retrieval_frame.get("instrument_hints"), list) else [],
        "applied_context_pack_template_ids": retrieval_frame.get("applied_context_pack_template_ids")
        if isinstance(retrieval_frame.get("applied_context_pack_template_ids"), list)
        else [],
    }

    selection_obj, selection_tool_run_id, selection_errs = deps.llm_structured_sync(
        prompt_id="context_assembly.select_evidence",
        prompt_version=1,
        prompt_name="Context Assembly: select evidence atoms",
        purpose="Select diverse, cited evidence atoms (including countervailing evidence) for Move 3 under a framing.",
        system_template=sys,
        user_payload=selection_payload,
        time_budget_seconds=min(120.0, max(10.0, time_budget_seconds)),
        temperature=0.65,
        max_tokens=1700,
        output_schema_ref="schemas/ContextAssemblySelection.schema.json",
    )
    selection_errs = selection_errs if isinstance(selection_errs, list) else []
    if isinstance(selection_tool_run_id, str):
        tool_run_ids.append(selection_tool_run_id)

    # Fallback selection if LLM unavailable/invalid: pick the top evidence_per_issue candidates per issue.
    selections_in = selection_obj.get("selections") if isinstance(selection_obj, dict) else None
    selection_by_issue: dict[str, dict[str, list[str]]] = {}
    if isinstance(selections_in, list):
        for item in selections_in:
            if not isinstance(item, dict):
                continue
            iid = item.get("issue_id")
            if not isinstance(iid, str) or not iid:
                continue
            selection_by_issue[iid] = {
                "supporting": [r for r in _safe_list_of_str(item.get("supporting_evidence_refs"), limit=40) if r in allowed_refs],
                "countervailing": [r for r in _safe_list_of_str(item.get("countervailing_evidence_refs"), limit=40) if r in allowed_refs],
                "contextual": [r for r in _safe_list_of_str(item.get("contextual_evidence_refs"), limit=40) if r in allowed_refs],
            }

    if not selection_by_issue:
        # deterministic fallback (logged via selection_errs/tool run)
        for issue in issues:
            iid = _safe_issue_id(issue)
            if not iid:
                continue
            refs = candidates_by_issue.get(iid, [])[: evidence_per_issue]
            selection_by_issue[iid] = {"supporting": refs, "countervailing": [], "contextual": []}

    # Coverage enforcement (normative): if countervailing candidates exist but none were selected, re-prompt for those issues only.
    issues_needing_rerun: list[dict[str, Any]] = []
    for issue in issues:
        iid = _safe_issue_id(issue)
        if not iid:
            continue
        sel = selection_by_issue.get(iid) or {}
        has_supporting = bool(sel.get("supporting"))
        has_counter = bool(sel.get("countervailing"))
        issue_candidates = candidates_by_issue.get(iid, [])
        counter_candidates = [
            ev
            for ev in issue_candidates
            if isinstance(ev, str) and (candidate_by_ref.get(ev) or {}).get("query_purpose") == "countervailing"
        ]
        if counter_candidates and not has_counter:
            issues_needing_rerun.append(
                {
                    "issue_id": iid,
                    "title": issue.get("title"),
                    "why_material": issue.get("why_material"),
                    "candidate_evidence": [
                        {
                            "evidence_ref": ev,
                            "type": (candidate_by_ref.get(ev) or {}).get("candidate_type"),
                            "title": (candidate_by_ref.get(ev) or {}).get("title"),
                            "summary": (candidate_by_ref.get(ev) or {}).get("summary") or (candidate_by_ref.get(ev) or {}).get("snippet"),
                            "query_purpose": (candidate_by_ref.get(ev) or {}).get("query_purpose"),
                        }
                        for ev in issue_candidates[:max_candidates_per_query]
                    ],
                    "countervailing_candidate_refs": counter_candidates[:25],
                    "previous_selection": sel,
                    "must_add_countervailing": True,
                    "must_add_supporting": not has_supporting,
                }
            )

    if issues_needing_rerun:
        rerun_sys = (
            "You are the Scout agent for The Planner's Assistant.\n"
            "Task: patch evidence selection for the issues below.\n"
            "You are being asked because the prior selection missed REQUIRED coverage.\n"
            "Return ONLY valid JSON compatible with schemas/ContextAssemblySelection.schema.json.\n"
            "Rules:\n"
            "- You MUST only choose evidence_refs that appear in the provided candidate lists.\n"
            "- For each issue marked must_add_countervailing=true: choose at least 1 countervailing_evidence_ref from countervailing_candidate_refs.\n"
            "- If must_add_supporting=true: choose at least 1 supporting_evidence_ref.\n"
            "- Keep changes minimal: prefer adding 1–2 items rather than rewriting the whole set.\n"
            "- Do not invent citations.\n"
        )
        rerun_payload = {
            "run_id": run_id,
            "authority_id": authority_id,
            "plan_cycle_id": plan_cycle_id,
            "scenario": scenario,
            "political_framing": framing,
            "max_atoms_per_issue": max_atoms_per_issue,
            "issues": issues_needing_rerun[:12],
            "instrument_hints": selection_payload.get("instrument_hints") or [],
        }
        rerun_obj, rerun_tool_run_id, rerun_errs = deps.llm_structured_sync(
            prompt_id="context_assembly.select_evidence.patch_missing_countervailing",
            prompt_version=1,
            prompt_name="Context Assembly: patch missing countervailing",
            purpose="Ensure countervailing coverage when candidates exist (planner-shaped, normative).",
            system_template=rerun_sys,
            user_payload=rerun_payload,
            time_budget_seconds=min(90.0, max(10.0, time_budget_seconds)),
            temperature=0.55,
            max_tokens=1200,
            output_schema_ref="schemas/ContextAssemblySelection.schema.json",
        )
        if isinstance(rerun_tool_run_id, str):
            tool_run_ids.append(rerun_tool_run_id)
        if isinstance(rerun_errs, list):
            selection_errs.extend([str(e) for e in rerun_errs[:10]])

        rerun_selections = rerun_obj.get("selections") if isinstance(rerun_obj, dict) else None
        if isinstance(rerun_selections, list):
            for item in rerun_selections:
                if not isinstance(item, dict):
                    continue
                iid = item.get("issue_id")
                if not isinstance(iid, str) or not iid:
                    continue
                selection_by_issue[iid] = {
                    "supporting": [
                        r
                        for r in _safe_list_of_str(item.get("supporting_evidence_refs"), limit=40)
                        if r in allowed_refs
                    ],
                    "countervailing": [
                        r
                        for r in _safe_list_of_str(item.get("countervailing_evidence_refs"), limit=40)
                        if r in allowed_refs
                    ],
                    "contextual": [
                        r
                        for r in _safe_list_of_str(item.get("contextual_evidence_refs"), limit=40)
                        if r in allowed_refs
                    ],
                }

    # Materialise EvidenceAtoms deterministically from selected evidence refs.
    evidence_atom_id_by_ref: dict[str, str] = {}
    evidence_atoms: list[dict[str, Any]] = []
    evidence_by_issue: list[dict[str, Any]] = []
    roles: dict[str, set[str]] = {"supporting": set(), "countervailing": set(), "contextual": set()}

    def ensure_atom_for_ref(evidence_ref: str) -> str | None:
        if evidence_ref in evidence_atom_id_by_ref:
            return evidence_atom_id_by_ref[evidence_ref]
        cand = candidate_by_ref.get(evidence_ref)
        if not isinstance(cand, dict):
            return None
        atom_id = str(uuid4())
        evidence_atom_id_by_ref[evidence_ref] = atom_id

        candidate_type = cand.get("candidate_type")
        artifact_ref: str | None = None
        if candidate_type == "instrument_output":
            title = cand.get("title") if isinstance(cand.get("title"), str) else "Instrument output"
            limitations = cand.get("limitations_text") if isinstance(cand.get("limitations_text"), str) else ""
            if not limitations.strip():
                limitations = "Instrument output; verify limitations and provenance."
            evidence_type = "instrument_output"
            metadata = {
                "tool_request_id": cand.get("tool_request_id"),
                "tool_run_id": cand.get("tool_run_id"),
                "tool_name": cand.get("tool_name"),
                "instrument_id": cand.get("instrument_id"),
                "outputs": cand.get("outputs") if isinstance(cand.get("outputs"), dict) else {},
                "scores": cand.get("scores"),
            }
        elif candidate_type == "site_fingerprint":
            title = f"Site fingerprint · {cand.get('site_id')}"
            limitations = cand.get("limitations_text") if isinstance(cand.get("limitations_text"), str) else ""
            if not limitations.strip():
                limitations = "Deterministic spatial fingerprint; verify constraint layer completeness."
            evidence_type = "instrument_output"
            metadata = {
                "site_id": cand.get("site_id"),
                "tool_run_id": cand.get("tool_run_id"),
                "fingerprint": cand.get("fingerprint") if isinstance(cand.get("fingerprint"), dict) else {},
                "scores": cand.get("scores"),
            }
        elif candidate_type == "spatial_feature":
            title = cand.get("title") if isinstance(cand.get("title"), str) else "Spatial feature"
            limitations = cand.get("limitations_text") if isinstance(cand.get("limitations_text"), str) else ""
            if not limitations.strip():
                limitations = "SpatialFeature from canonical store; verify applicability, temporal validity, and completeness."
            evidence_type = "spatial_feature"
            metadata = {
                "site_id": cand.get("site_id"),
                "spatial_feature_id": cand.get("spatial_feature_id"),
                "feature_type": cand.get("feature_type"),
                "spatial_scope": cand.get("spatial_scope"),
                "properties": cand.get("properties") if isinstance(cand.get("properties"), dict) else {},
                "scores": cand.get("scores"),
            }
        elif candidate_type == "visual_asset":
            title = cand.get("title") if isinstance(cand.get("title"), str) else "Visual evidence"
            limitations = (
                "Visual asset retrieved from the canonical store. Interpretation requires a VLM instrument run; "
                "treat relevance as provisional until inspected."
            )
            evidence_type = "visual_asset"
            metadata = {
                "visual_asset_id": cand.get("visual_asset_id"),
                "asset_type": cand.get("asset_type"),
                "page_number": cand.get("page_number"),
                "document_id": cand.get("document_id"),
                "document_title": cand.get("document_title"),
                "blob_path": cand.get("blob_path"),
                "asset_metadata": cand.get("asset_metadata") if isinstance(cand.get("asset_metadata"), dict) else {},
                "scores": cand.get("scores"),
            }
            artifact_ref = cand.get("blob_path") if isinstance(cand.get("blob_path"), str) else None
        elif candidate_type == "policy_clause":
            title = f"{cand.get('policy_ref') or cand.get('clause_ref') or 'Policy clause'} · {cand.get('document_title') or 'Policy'}"
            limitations = (
                "Policy clause retrieved as an evidence candidate; verify wording, status/weight, and plan-cycle applicability."
            )
            evidence_type = "policy_clause"
            metadata: dict[str, Any] = {
                "policy_clause_id": cand.get("policy_clause_id"),
                "policy_section_id": cand.get("policy_section_id"),
                "clause_ref": cand.get("clause_ref"),
                "policy_ref": cand.get("policy_ref"),
                "policy_title": cand.get("policy_title"),
                "document_title": cand.get("document_title"),
                "section_path": cand.get("section_path"),
                "speech_act": cand.get("speech_act"),
                "scores": cand.get("scores"),
            }
        else:
            title = f"{cand.get('document_title') or 'Document'} · p{cand.get('page_number') or '?'}"
            limitations = "Retrieved excerpt; relevance is a candidate for planner review."
            evidence_type = "doc_chunk"
            metadata = {
                "chunk_id": cand.get("chunk_id"),
                "document_title": cand.get("document_title"),
                "page_number": cand.get("page_number"),
                "section_path": cand.get("section_path"),
                "scores": cand.get("scores"),
            }

        summary = cand.get("summary") if isinstance(cand.get("summary"), str) else ""
        if not summary:
            summary = cand.get("snippet") if isinstance(cand.get("snippet"), str) else ""

        # Hydrate direct-source excerpt text (planner-friendly VLEC). This is evidence, not interpretation.
        try:
            if candidate_type == "instrument_output" and isinstance(cand.get("tool_run_id"), str) and isinstance(metadata, dict):
                row = deps.db_fetch_one(
                    """
                    SELECT tool_name, outputs_logged, confidence_hint, uncertainty_note
                    FROM tool_runs
                    WHERE id = %s::uuid
                    """,
                    (cand.get("tool_run_id"),),
                )
                if row:
                    metadata["tool_name"] = row.get("tool_name")
                    metadata["tool_outputs_logged"] = row.get("outputs_logged") if isinstance(row.get("outputs_logged"), dict) else {}
                    metadata["confidence_hint"] = row.get("confidence_hint")
                    metadata["uncertainty_note"] = row.get("uncertainty_note")

            if candidate_type == "spatial_feature" and isinstance(cand.get("spatial_feature_id"), str) and isinstance(metadata, dict):
                row = deps.db_fetch_one(
                    """
                    SELECT
                      type,
                      spatial_scope,
                      effective_from,
                      effective_to,
                      confidence_hint,
                      uncertainty_note,
                      properties
                    FROM spatial_features
                    WHERE id = %s::uuid
                    """,
                    (cand.get("spatial_feature_id"),),
                )
                if row:
                    metadata["feature_type"] = row.get("type")
                    metadata["spatial_scope"] = row.get("spatial_scope")
                    metadata["effective_from"] = row.get("effective_from")
                    metadata["effective_to"] = row.get("effective_to")
                    metadata["confidence_hint"] = row.get("confidence_hint")
                    metadata["uncertainty_note"] = row.get("uncertainty_note")
                    if isinstance(row.get("properties"), dict):
                        metadata["properties"] = row.get("properties")

            if candidate_type == "policy_clause" and isinstance(cand.get("policy_clause_id"), str):
                row = deps.db_fetch_one(
                    """
                    SELECT
                      pc.text AS clause_text,
                      pc.speech_act_jsonb AS speech_act,
                      ps.policy_code,
                      ps.title AS policy_title,
                      d.document_status,
                      d.weight_hint,
                      d.effective_from,
                      d.effective_to,
                      d.uncertainty_note,
                      d.confidence_hint
                    FROM policy_clauses pc
                    JOIN policy_sections ps ON ps.id = pc.policy_section_id
                    JOIN documents d ON d.id = ps.document_id
                    WHERE pc.id = %s::uuid
                    """,
                    (cand.get("policy_clause_id"),),
                )
                if row and isinstance(metadata, dict):
                    clause_text = row.get("clause_text")
                    if isinstance(clause_text, str) and clause_text.strip():
                        metadata["excerpt_text"] = _trim_text(clause_text, max_chars=5000)
                        metadata["excerpt_source"] = "policy_clauses.text"
                    metadata["policy_code"] = row.get("policy_code")
                    metadata["policy_title"] = row.get("policy_title")
                    metadata["speech_act"] = row.get("speech_act")
                    metadata["document_status"] = row.get("document_status")
                    metadata["document_weight_hint"] = row.get("weight_hint")
                    metadata["effective_from"] = row.get("effective_from")
                    metadata["effective_to"] = row.get("effective_to")
                    metadata["confidence_hint"] = row.get("confidence_hint")
                    metadata["uncertainty_note"] = row.get("uncertainty_note")
            if candidate_type != "policy_clause" and isinstance(cand.get("chunk_id"), str) and isinstance(metadata, dict):
                row = deps.db_fetch_one(
                    """
                    SELECT
                      c.text AS chunk_text,
                      c.bbox,
                      c.type,
                      c.metadata AS chunk_metadata,
                      d.document_status,
                      d.weight_hint,
                      d.effective_from,
                      d.effective_to,
                      d.confidence_hint,
                      d.uncertainty_note
                    FROM chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE c.id = %s::uuid
                    """,
                    (cand.get("chunk_id"),),
                )
                if row:
                    chunk_text = row.get("chunk_text")
                    if isinstance(chunk_text, str) and chunk_text.strip():
                        metadata["excerpt_text"] = _trim_text(chunk_text, max_chars=5000)
                        metadata["excerpt_source"] = "chunks.text"
                    metadata["bbox"] = row.get("bbox")
                    metadata["chunk_type"] = row.get("type")
                    metadata["chunk_metadata"] = row.get("chunk_metadata") if isinstance(row.get("chunk_metadata"), dict) else {}
                    metadata["document_status"] = row.get("document_status")
                    metadata["document_weight_hint"] = row.get("weight_hint")
                    metadata["effective_from"] = row.get("effective_from")
                    metadata["effective_to"] = row.get("effective_to")
                    metadata["confidence_hint"] = row.get("confidence_hint")
                    metadata["uncertainty_note"] = row.get("uncertainty_note")
        except Exception:  # noqa: BLE001
            pass

        evidence_atoms.append(
            {
                "evidence_atom_id": atom_id,
                "evidence_type": evidence_type,
                "title": title,
                "summary": summary,
                "evidence_ref": evidence_ref,
                "metadata": metadata,
                "limitations_text": limitations,
                **({"artifact_ref": artifact_ref} if artifact_ref else {}),
            }
        )
        return atom_id

    for issue in issues:
        iid = _safe_issue_id(issue)
        if not iid:
            continue
        sel = selection_by_issue.get(iid) or {"supporting": [], "countervailing": [], "contextual": []}
        atoms_for_issue: list[str] = []
        for role in ("supporting", "countervailing", "contextual"):
            for ev in sel.get(role, [])[:max_atoms_per_issue]:
                atom_id = ensure_atom_for_ref(ev)
                if not atom_id:
                    continue
                roles[role].add(ev)
                atoms_for_issue.append(atom_id)
        # de-dupe while preserving order
        seen: set[str] = set()
        atoms_for_issue = [a for a in atoms_for_issue if not (a in seen or seen.add(a))]
        evidence_by_issue.append({"issue_id": iid, "evidence_atom_ids": atoms_for_issue[:max_atoms_per_issue]})

    omissions: list[dict[str, Any]] = []
    if isinstance(selection_obj, dict):
        for block in [selection_obj.get("global_deliberate_omissions")] + [
            (x.get("deliberate_omissions") if isinstance(x, dict) else None) for x in (selections_in or [])
        ]:
            if not isinstance(block, list):
                continue
            for o in block[:30]:
                if not isinstance(o, dict):
                    continue
                desc = o.get("description")
                reason = o.get("reason")
                if not isinstance(desc, str) or not isinstance(reason, str):
                    continue
                omissions.append(
                    {
                        "omission_id": str(uuid4()),
                        "description": desc.strip(),
                        "reason": reason.strip(),
                        "would_have_addressed_issue_ids": [
                            x for x in _safe_list_of_str(o.get("would_have_addressed_issue_ids"), limit=12) if x
                        ],
                    }
                )

    tool_requests: list[dict[str, Any]] = []
    if isinstance(selection_obj, dict):
        blocks = [selection_obj.get("global_tool_requests")] + [
            (x.get("tool_requests") if isinstance(x, dict) else None) for x in (selections_in or [])
        ]
        for block in blocks:
            if not isinstance(block, list):
                continue
            for tr in block[:40]:
                if not isinstance(tr, dict):
                    continue
                purpose = tr.get("purpose")
                inputs = tr.get("inputs")
                if not isinstance(purpose, str) or not isinstance(inputs, dict):
                    continue
                tool_requests.append(
                    {
                        "tool_request_id": str(uuid4()),
                        "tool_name": tr.get("tool_name") if isinstance(tr.get("tool_name"), str) else "request_instrument",
                        "instrument_id": tr.get("instrument_id") if isinstance(tr.get("instrument_id"), str) else "",
                        "inputs": inputs,
                        "purpose": purpose.strip(),
                        "blocking": bool(tr.get("blocking")) if tr.get("blocking") is not None else True,
                        "requested_by_move_type": "evidence_curation",
                        "requested_at": deps.utc_now_iso(),
                    }
                )

    # Template-driven tool request seeding (planner heuristics): if issues strongly suggest an instrument and inputs exist,
    # add non-blocking requests so tool use is executable, not aspirational.
    existing_instrument_ids = {tr.get("instrument_id") for tr in tool_requests if isinstance(tr, dict)}
    existing_instrument_ids = {x for x in existing_instrument_ids if isinstance(x, str) and x.strip()}
    site_ids_for_tools = extract_site_ids_from_state_vector(scenario.get("state_vector") if isinstance(scenario, dict) else {})

    def issue_text(issue: dict[str, Any]) -> str:
        parts = []
        for k in ("title", "why_material"):
            v = issue.get(k)
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
        return " ".join(parts).lower()

    instrument_hints = retrieval_frame.get("instrument_hints") if isinstance(retrieval_frame.get("instrument_hints"), list) else []
    for hint in instrument_hints[:30]:
        if not isinstance(hint, dict):
            continue
        instrument_id = hint.get("instrument_id")
        if not isinstance(instrument_id, str) or not instrument_id.strip():
            continue
        if instrument_id in existing_instrument_ids:
            continue
        keywords = hint.get("when_issue_keywords")
        keywords = [k.strip().lower() for k in keywords if isinstance(k, str) and k.strip()] if isinstance(keywords, list) else []
        if not keywords:
            continue
        matched = any(any(k in issue_text(i) for k in keywords) for i in issues[:20])
        if not matched:
            continue

        if instrument_id in {"dft_connectivity", "environment_agency_flood"} and not site_ids_for_tools:
            # No geometries to run against yet; leave for the LLM to request later once sites exist.
            continue

        if instrument_id == "townscape_vlm_assessment":
            selected_visual_refs = [a.get("evidence_ref") for a in evidence_atoms if isinstance(a, dict) and str(a.get("evidence_type")) == "visual_asset"]
            selected_visual_refs = [r for r in selected_visual_refs if isinstance(r, str)]
            if not selected_visual_refs:
                continue
            tool_requests.append(
                {
                    "tool_request_id": str(uuid4()),
                    "tool_name": "request_instrument",
                    "instrument_id": "townscape_vlm_assessment",
                    "inputs": {"visual_asset_refs": selected_visual_refs[:6], "viewpoint_context": {"work_mode": work_mode}},
                    "purpose": hint.get("purpose") or "Townscape/visual assessment (VLM instrument).",
                    "blocking": bool(hint.get("blocking")) if hint.get("blocking") is not None else False,
                    "requested_by_move_type": "evidence_curation",
                    "requested_at": deps.utc_now_iso(),
                }
            )
            existing_instrument_ids.add(instrument_id)
            continue

        # Site-scoped instruments: one request per site (bounded).
        for site_id in site_ids_for_tools[:3]:
            tool_requests.append(
                {
                    "tool_request_id": str(uuid4()),
                    "tool_name": "request_instrument",
                    "instrument_id": instrument_id,
                    "inputs": {"site_id": site_id, "authority_id": authority_id, "plan_cycle_id": plan_cycle_id},
                    "purpose": hint.get("purpose") or f"Run instrument {instrument_id}.",
                    "blocking": bool(hint.get("blocking")) if hint.get("blocking") is not None else False,
                    "requested_by_move_type": "evidence_curation",
                    "requested_at": deps.utc_now_iso(),
                }
            )
        existing_instrument_ids.add(instrument_id)

    curated = {
        "curated_evidence_set_id": str(uuid4()),
        "evidence_atoms": evidence_atoms,
        "evidence_by_issue": evidence_by_issue,
        "deliberate_omissions": omissions,
        "tool_requests": tool_requests,
    }

    return {
        "retrieval_frame": retrieval_frame,
        "curated_evidence_set": curated,
        "tool_run_ids": tool_run_ids,
        "evidence_roles": {k: sorted(list(v)) for k, v in roles.items()},
        "selection_errors": selection_errs[:10] if isinstance(selection_errs, list) else [],
    }
