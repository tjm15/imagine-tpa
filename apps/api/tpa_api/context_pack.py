from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .evidence import _ensure_evidence_ref_row
from .spec_io import _read_yaml, _spec_root
from .text_utils import _estimate_tokens

MoveType = str


@dataclass(frozen=True)
class ContextPackAssemblyDeps:
    db_fetch_one: Callable[[str, tuple[Any, ...] | list[Any] | None], dict[str, Any] | None]
    db_fetch_all: Callable[[str, tuple[Any, ...] | list[Any] | None], list[dict[str, Any]]]
    db_execute: Callable[[str, tuple[Any, ...] | list[Any] | None], None]
    llm_structured_sync: Callable[..., tuple[dict[str, Any] | None, str | None, list[str]]]
    utc_now_iso: Callable[[], str]
    utc_now: Callable[[], Any]


_CONTEXT_SELECTOR_CACHE: tuple[float, dict[str, Any]] | None = None
_GOOD_PRACTICE_CACHE: tuple[float, dict[str, Any]] | None = None


def _load_context_selector_registry() -> dict[str, Any]:
    global _CONTEXT_SELECTOR_CACHE  # noqa: PLW0603

    try:
        path = (_spec_root() / "capabilities" / "CONTEXT_SELECTOR_REGISTRY.yaml").resolve()
        mtime = path.stat().st_mtime
    except Exception:  # noqa: BLE001
        return {"selectors": [], "selection_policy": {}}

    if _CONTEXT_SELECTOR_CACHE and _CONTEXT_SELECTOR_CACHE[0] == mtime:
        return _CONTEXT_SELECTOR_CACHE[1]

    try:
        data = _read_yaml(Path(path))
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}
    _CONTEXT_SELECTOR_CACHE = (mtime, data)
    return data


def _load_good_practice_cards() -> dict[str, Any]:
    global _GOOD_PRACTICE_CACHE  # noqa: PLW0603

    try:
        path = (_spec_root() / "governance" / "GOOD_PRACTICE_CARDS.yaml").resolve()
        mtime = path.stat().st_mtime
    except Exception:  # noqa: BLE001
        return {"cards": []}

    if _GOOD_PRACTICE_CACHE and _GOOD_PRACTICE_CACHE[0] == mtime:
        return _GOOD_PRACTICE_CACHE[1]

    try:
        data = _read_yaml(Path(path))
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}
    _GOOD_PRACTICE_CACHE = (mtime, data)
    return data


def _resolve_context_selector(*, work_mode: str, move_type: MoveType) -> dict[str, Any] | None:
    data = _load_context_selector_registry()
    selectors = data.get("selectors") if isinstance(data, dict) else None
    if not isinstance(selectors, list):
        return None
    for selector in selectors:
        if not isinstance(selector, dict):
            continue
        if selector.get("work_mode") != work_mode:
            continue
        if selector.get("move_type") != move_type:
            continue
        return selector
    return None


def _estimate_payload_tokens(payload: dict[str, Any]) -> int:
    try:
        return _estimate_tokens(json.dumps(payload, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        return 0


def _gate_slice_availability(
    *,
    deps: ContextPackAssemblyDeps,
    authority_id: str | None,
    plan_cycle_id: str | None,
    plan_project_id: str | None,
    application_id: str | None,
) -> dict[str, bool]:
    status = {
        "visual_assets_present": False,
        "spatial_layers_present": False,
        "consultations_present": False,
        "decisions_present": False,
    }

    try:
        status["visual_assets_present"] = (
            deps.db_fetch_one(
                """
                SELECT 1
                FROM visual_assets va
                JOIN documents d ON d.id = va.document_id
                WHERE d.is_active = true
                  AND (%s IS NULL OR d.authority_id = %s)
                  AND (%s::uuid IS NULL OR d.plan_cycle_id = %s::uuid)
                LIMIT 1
                """,
                (authority_id, authority_id, plan_cycle_id, plan_cycle_id),
            )
            is not None
        )
    except Exception:  # noqa: BLE001
        status["visual_assets_present"] = False

    try:
        status["spatial_layers_present"] = (
            deps.db_fetch_one(
                """
                SELECT 1
                FROM spatial_features sf
                WHERE sf.is_active = true
                  AND (%s IS NULL OR sf.authority_id = %s)
                LIMIT 1
                """,
                (authority_id, authority_id),
            )
            is not None
        )
    except Exception:  # noqa: BLE001
        status["spatial_layers_present"] = False

    try:
        status["consultations_present"] = (
            deps.db_fetch_one(
                """
                SELECT 1
                FROM consultations c
                WHERE (%s::uuid IS NULL OR c.plan_project_id = %s::uuid)
                LIMIT 1
                """,
                (plan_project_id, plan_project_id),
            )
            is not None
        )
    except Exception:  # noqa: BLE001
        status["consultations_present"] = False

    try:
        status["decisions_present"] = (
            deps.db_fetch_one(
                """
                SELECT 1
                FROM decisions d
                WHERE (%s::uuid IS NULL OR d.application_id = %s::uuid)
                LIMIT 1
                """,
                (application_id, application_id),
            )
            is not None
        )
    except Exception:  # noqa: BLE001
        status["decisions_present"] = False

    return status


def _apply_gating(slice_entry: dict[str, Any], gate_status: dict[str, bool]) -> bool:
    gating = slice_entry.get("gating")
    if not isinstance(gating, list) or not gating:
        return True
    for gate in gating:
        if isinstance(gate, str) and not gate_status.get(gate, False):
            return False
    return True


def _policy_clause_candidates(
    *,
    deps: ContextPackAssemblyDeps,
    authority_id: str | None,
    plan_cycle_id: str | None,
) -> list[dict[str, Any]]:
    rows = deps.db_fetch_all(
        """
        SELECT
          pc.id AS policy_clause_id,
          pc.clause_ref,
          pc.text,
          pc.metadata_jsonb AS clause_metadata,
          ps.id AS policy_section_id,
          ps.policy_code AS policy_ref,
          ps.section_path,
          d.metadata->>'title' AS document_title,
          d.document_status,
          d.weight_hint,
          er.source_type,
          er.source_id,
          er.fragment_id
        FROM policy_clauses pc
        JOIN policy_sections ps ON ps.id = pc.policy_section_id
        JOIN documents d ON d.id = ps.document_id
        LEFT JOIN evidence_refs er ON er.id = pc.evidence_ref_id
        WHERE d.is_active = true
          AND (%s IS NULL OR d.authority_id = %s)
          AND (%s::uuid IS NULL OR d.plan_cycle_id = %s::uuid)
        ORDER BY d.metadata->>'title' ASC NULLS LAST, ps.section_path ASC NULLS LAST, pc.clause_ref ASC NULLS LAST
        """,
        (authority_id, authority_id, plan_cycle_id, plan_cycle_id),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        clause_id = str(row.get("policy_clause_id") or "")
        if not clause_id:
            continue
        source_type = row.get("source_type")
        source_id = row.get("source_id")
        fragment_id = row.get("fragment_id")
        if source_type and source_id and fragment_id:
            evidence_ref = f"{source_type}::{source_id}::{fragment_id}"
        else:
            evidence_ref = f"policy_clause::{clause_id}::text"
            _ensure_evidence_ref_row(evidence_ref)
        text = row.get("text") if isinstance(row.get("text"), str) else ""
        summary = text
        title_bits = [row.get("policy_ref"), row.get("clause_ref")]
        title = " ".join([b for b in title_bits if isinstance(b, str) and b.strip()]) or row.get("document_title") or "Policy clause"
        payload = {
            "policy_clause_id": clause_id,
            "policy_section_id": str(row.get("policy_section_id")) if row.get("policy_section_id") else None,
            "policy_ref": row.get("policy_ref"),
            "clause_ref": row.get("clause_ref"),
            "section_path": row.get("section_path"),
            "text": text,
            "document_title": row.get("document_title"),
            "document_status": row.get("document_status"),
            "weight_hint": row.get("weight_hint"),
            "evidence_ref": evidence_ref,
            "tool_run_id": None,
            "confidence_hint": None,
            "limitations_text": None,
            "metadata": row.get("clause_metadata") if isinstance(row.get("clause_metadata"), dict) else {},
        }
        out.append(
            {
                "candidate_id": f"policy_clause::{clause_id}",
                "slice_type": "policy_clauses",
                "evidence_ref": evidence_ref,
                "approx_tokens": _estimate_payload_tokens(payload),
                "summary": summary,
                "title": title,
                "payload": payload,
            }
        )
    return out


def _evidence_atom_candidates(
    *,
    deps: ContextPackAssemblyDeps,
    run_id: str,
) -> list[dict[str, Any]]:
    row = deps.db_fetch_one(
        """
        SELECT outputs_jsonb
        FROM move_events
        WHERE run_id = %s::uuid
          AND move_type = 'evidence_curation'
        ORDER BY sequence DESC
        LIMIT 1
        """,
        (run_id,),
    )
    outputs = row.get("outputs_jsonb") if isinstance(row, dict) else None
    curated = outputs.get("curated_evidence_set") if isinstance(outputs, dict) else None
    atoms = curated.get("evidence_atoms") if isinstance(curated, dict) else None
    if not isinstance(atoms, list):
        return []
    out: list[dict[str, Any]] = []
    for atom in atoms:
        if not isinstance(atom, dict):
            continue
        atom_id = atom.get("evidence_atom_id") if isinstance(atom.get("evidence_atom_id"), str) else str(uuid4())
        evidence_ref = atom.get("evidence_ref") if isinstance(atom.get("evidence_ref"), str) else None
        if not evidence_ref:
            continue
        summary = atom.get("summary") if isinstance(atom.get("summary"), str) else ""
        title = atom.get("title") if isinstance(atom.get("title"), str) else "Evidence"
        out.append(
            {
                "candidate_id": f"evidence_atom::{atom_id}",
                "slice_type": "evidence_atoms",
                "evidence_ref": evidence_ref,
                "approx_tokens": _estimate_payload_tokens(atom),
                "summary": summary,
                "title": title,
                "payload": atom,
            }
        )
    return out


def _visual_asset_candidates(
    *,
    deps: ContextPackAssemblyDeps,
    authority_id: str | None,
    plan_cycle_id: str | None,
) -> list[dict[str, Any]]:
    rows = deps.db_fetch_all(
        """
        SELECT
          va.id AS visual_asset_id,
          va.asset_type,
          va.page_number,
          va.metadata AS asset_metadata,
          d.id AS document_id,
          d.metadata->>'title' AS document_title,
          er.source_type,
          er.source_id,
          er.fragment_id,
          vs.agent_findings_jsonb,
          vs.asset_specific_facts_jsonb,
          vre.interpretation_notes
        FROM visual_assets va
        JOIN documents d ON d.id = va.document_id
        LEFT JOIN evidence_refs er ON er.id = va.evidence_ref_id
        LEFT JOIN LATERAL (
          SELECT agent_findings_jsonb, asset_specific_facts_jsonb
          FROM visual_semantic_outputs vso
          WHERE vso.visual_asset_id = va.id
          ORDER BY vso.created_at DESC NULLS LAST
          LIMIT 1
        ) vs ON TRUE
        LEFT JOIN LATERAL (
          SELECT interpretation_notes
          FROM visual_rich_enrichments vre
          WHERE vre.visual_asset_id = va.id
          ORDER BY vre.created_at DESC NULLS LAST
          LIMIT 1
        ) vre ON TRUE
        WHERE d.is_active = true
          AND (%s IS NULL OR d.authority_id = %s)
          AND (%s::uuid IS NULL OR d.plan_cycle_id = %s::uuid)
        ORDER BY d.metadata->>'title' ASC NULLS LAST, va.page_number ASC NULLS LAST
        """,
        (authority_id, authority_id, plan_cycle_id, plan_cycle_id),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        asset_id = str(row.get("visual_asset_id") or "")
        if not asset_id:
            continue
        source_type = row.get("source_type")
        source_id = row.get("source_id")
        fragment_id = row.get("fragment_id")
        if source_type and source_id and fragment_id:
            evidence_ref = f"{source_type}::{source_id}::{fragment_id}"
        else:
            evidence_ref = f"visual_asset::{asset_id}::blob"
            _ensure_evidence_ref_row(evidence_ref)
        findings = row.get("agent_findings_jsonb") if isinstance(row.get("agent_findings_jsonb"), dict) else {}
        facts = row.get("asset_specific_facts_jsonb") if isinstance(row.get("asset_specific_facts_jsonb"), dict) else {}
        notes = row.get("interpretation_notes") if isinstance(row.get("interpretation_notes"), str) else ""
        summary_bits = []
        if notes:
            summary_bits.append(notes)
        if findings:
            summary_bits.append(json.dumps(findings, ensure_ascii=False))
        if facts and not summary_bits:
            summary_bits.append(json.dumps(facts, ensure_ascii=False))
        summary = " ".join([b for b in summary_bits if isinstance(b, str) and b.strip()])
        title_bits = [
            row.get("document_title") or "Document",
            f"p{row.get('page_number')}" if row.get("page_number") else None,
            row.get("asset_type") or "visual",
        ]
        title = " · ".join([b for b in title_bits if isinstance(b, str) and b.strip()])
        payload = {
            "visual_asset_id": asset_id,
            "document_id": str(row.get("document_id")) if row.get("document_id") else None,
            "document_title": row.get("document_title"),
            "page_number": row.get("page_number"),
            "asset_type": row.get("asset_type"),
            "evidence_ref": evidence_ref,
            "tool_run_id": None,
            "metadata": row.get("asset_metadata") if isinstance(row.get("asset_metadata"), dict) else {},
        }
        out.append(
            {
                "candidate_id": f"visual_asset::{asset_id}",
                "slice_type": "visual_assets",
                "evidence_ref": evidence_ref,
                "approx_tokens": _estimate_payload_tokens(payload),
                "summary": summary,
                "title": title,
                "payload": payload,
            }
        )
    return out


def _spatial_feature_candidates(
    *,
    deps: ContextPackAssemblyDeps,
    authority_id: str | None,
) -> list[dict[str, Any]]:
    rows = deps.db_fetch_all(
        """
        SELECT
          sf.id AS spatial_feature_id,
          sf.type,
          sf.spatial_scope,
          sf.confidence_hint,
          sf.uncertainty_note,
          sf.properties
        FROM spatial_features sf
        WHERE sf.is_active = true
          AND (%s IS NULL OR sf.authority_id = %s)
        ORDER BY sf.type ASC
        """,
        (authority_id, authority_id),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        feature_id = str(row.get("spatial_feature_id") or "")
        if not feature_id:
            continue
        evidence_ref = f"spatial_feature::{feature_id}::properties"
        _ensure_evidence_ref_row(evidence_ref)
        props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
        summary = (
            props.get("interpreted_summary")
            if isinstance(props.get("interpreted_summary"), str)
            else None
        )
        if not summary:
            label = props.get("name") or props.get("title") or props.get("label")
            summary = f"{row.get('type')}: {label}" if label else f"{row.get('type')} spatial feature"
        summary = summary
        payload = {
            "spatial_feature_id": feature_id,
            "spatial_layer_id": None,
            "feature_type": row.get("type"),
            "spatial_scope": row.get("spatial_scope"),
            "summary": summary,
            "properties": props,
            "evidence_ref": evidence_ref,
            "tool_run_id": None,
            "confidence_hint": row.get("confidence_hint"),
            "limitations_text": row.get("uncertainty_note"),
        }
        out.append(
            {
                "candidate_id": f"spatial_feature::{feature_id}",
                "slice_type": "spatial_features",
                "evidence_ref": evidence_ref,
                "approx_tokens": _estimate_payload_tokens(payload),
                "summary": summary,
                "title": summary,
                "payload": payload,
            }
        )
    return out


def _consultation_candidates(
    *,
    deps: ContextPackAssemblyDeps,
    plan_project_id: str | None,
) -> list[dict[str, Any]]:
    rows = deps.db_fetch_all(
        """
        SELECT id, consultation_type, title, status, open_at, close_at
        FROM consultations
        WHERE (%s::uuid IS NULL OR plan_project_id = %s::uuid)
        ORDER BY open_at DESC NULLS LAST, created_at DESC
        """,
        (plan_project_id, plan_project_id),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        consultation_id = str(row.get("id") or "")
        if not consultation_id:
            continue
        evidence_ref = f"consultation::{consultation_id}::record"
        _ensure_evidence_ref_row(evidence_ref)
        title = row.get("title") if isinstance(row.get("title"), str) else "Consultation"
        summary = title
        payload = {
            "consultation_id": consultation_id,
            "consultation_type": row.get("consultation_type"),
            "title": row.get("title"),
            "status": row.get("status"),
            "open_at": row.get("open_at").isoformat() if row.get("open_at") else None,
            "close_at": row.get("close_at").isoformat() if row.get("close_at") else None,
            "evidence_ref": evidence_ref,
            "tool_run_id": None,
        }
        out.append(
            {
                "candidate_id": f"consultation::{consultation_id}",
                "slice_type": "consultations",
                "evidence_ref": evidence_ref,
                "approx_tokens": _estimate_payload_tokens(payload),
                "summary": summary,
                "title": title,
                "payload": payload,
            }
        )
    return out


def _decision_candidates(
    *,
    deps: ContextPackAssemblyDeps,
    application_id: str | None,
) -> list[dict[str, Any]]:
    rows = deps.db_fetch_all(
        """
        SELECT id, application_id, outcome, decision_date
        FROM decisions
        WHERE (%s::uuid IS NULL OR application_id = %s::uuid)
        ORDER BY decision_date DESC NULLS LAST
        """,
        (application_id, application_id),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        decision_id = str(row.get("id") or "")
        if not decision_id:
            continue
        evidence_ref = f"decision::{decision_id}::record"
        _ensure_evidence_ref_row(evidence_ref)
        summary = f"Decision {row.get('outcome')}"
        payload = {
            "decision_id": decision_id,
            "application_id": str(row.get("application_id")) if row.get("application_id") else None,
            "outcome": row.get("outcome"),
            "decision_date": row.get("decision_date").isoformat() if row.get("decision_date") else None,
            "evidence_ref": evidence_ref,
            "tool_run_id": None,
        }
        out.append(
            {
                "candidate_id": f"decision::{decision_id}",
                "slice_type": "decisions",
                "evidence_ref": evidence_ref,
                "approx_tokens": _estimate_payload_tokens(payload),
                "summary": summary,
                "title": summary,
                "payload": payload,
            }
        )
    return out


def _advice_card_candidates(
    *,
    deps: ContextPackAssemblyDeps,
    authority_id: str | None,
    plan_cycle_id: str | None,
) -> list[dict[str, Any]]:
    if not authority_id:
        return []
    card_catalogue = _load_good_practice_cards()
    card_list = card_catalogue.get("cards") if isinstance(card_catalogue, dict) else []
    card_by_id = {c.get("card_id"): c for c in card_list if isinstance(c, dict) and isinstance(c.get("card_id"), str)}

    scope_rows = deps.db_fetch_all(
        """
        SELECT d.id AS scope_id, 'document' AS scope_type
        FROM documents d
        WHERE d.is_active = true
          AND d.authority_id = %s
          AND (%s::uuid IS NULL OR d.plan_cycle_id = %s::uuid)
        """,
        (authority_id, plan_cycle_id, plan_cycle_id),
    )
    scope_ids = [str(r.get("scope_id")) for r in scope_rows if r.get("scope_id")]
    if not scope_ids:
        return []

    rows = deps.db_fetch_all(
        """
        SELECT id, card_id, card_version, scope_type, scope_id, status,
               trigger_cues_jsonb, evidence_refs_jsonb, tool_run_id, notes, created_at
        FROM advice_card_instances
        WHERE scope_id = ANY(%s::uuid[])
        ORDER BY created_at DESC
        """,
        (scope_ids,),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        instance_id = str(row.get("id") or "")
        card_id = row.get("card_id") if isinstance(row.get("card_id"), str) else ""
        if not instance_id or not card_id:
            continue
        card = card_by_id.get(card_id, {})
        prompt = card.get("prompt") if isinstance(card.get("prompt"), str) else None
        title = card.get("title") if isinstance(card.get("title"), str) else None
        summary = prompt or title or card_id
        payload = {
            "instance_id": instance_id,
            "card_id": card_id,
            "card_title": title,
            "card_type": card.get("type"),
            "basis": card.get("basis"),
            "priority": card.get("priority"),
            "status": card.get("status"),
            "scope_type": row.get("scope_type"),
            "scope_id": str(row.get("scope_id")) if row.get("scope_id") else None,
            "prompt": prompt,
            "evidence_refs": row.get("evidence_refs_jsonb") if isinstance(row.get("evidence_refs_jsonb"), list) else [],
            "tool_run_id": str(row.get("tool_run_id")) if row.get("tool_run_id") else None,
            "notes": row.get("notes"),
        }
        out.append(
            {
                "candidate_id": f"advice_card::{instance_id}",
                "slice_type": "advice_cards",
                "evidence_ref": None,
                "approx_tokens": _estimate_payload_tokens(payload),
                "summary": summary,
                "title": title or card_id,
                "payload": payload,
            }
        )
    return out


def _assumption_candidates(*, deps: ContextPackAssemblyDeps, run_id: str) -> list[dict[str, Any]]:
    rows = deps.db_fetch_all(
        """
        SELECT assumptions_introduced_jsonb
        FROM move_events
        WHERE run_id = %s::uuid
          AND assumptions_introduced_jsonb IS NOT NULL
        ORDER BY sequence ASC
        """,
        (run_id,),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        items = row.get("assumptions_introduced_jsonb")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            assumption_id = item.get("assumption_id") if isinstance(item.get("assumption_id"), str) else str(uuid4())
            statement = item.get("statement") if isinstance(item.get("statement"), str) else ""
            summary = statement or "Assumption"
            payload = {
                "assumption_id": assumption_id,
                "statement": statement,
                "scope": item.get("scope") if isinstance(item.get("scope"), str) else "run",
                "justification": item.get("justification") if isinstance(item.get("justification"), str) else "",
                "type": item.get("type") if isinstance(item.get("type"), str) else "other",
                "evidence_refs": item.get("evidence_refs") if isinstance(item.get("evidence_refs"), list) else [],
                "tool_run_id": None,
            }
            out.append(
                {
                    "candidate_id": f"assumption::{assumption_id}",
                    "slice_type": "assumptions",
                    "evidence_ref": None,
                    "approx_tokens": _estimate_payload_tokens(payload),
                    "summary": summary,
                    "title": summary,
                    "payload": payload,
                }
            )
    return out


def _limitation_candidates(*, deps: ContextPackAssemblyDeps, run_id: str) -> list[dict[str, Any]]:
    rows = deps.db_fetch_all(
        """
        SELECT uncertainty_remaining_jsonb
        FROM move_events
        WHERE run_id = %s::uuid
          AND uncertainty_remaining_jsonb IS NOT NULL
        ORDER BY sequence ASC
        """,
        (run_id,),
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        items = row.get("uncertainty_remaining_jsonb")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, str) or not item.strip():
                continue
            limitation_id = str(uuid4())
            summary = item
            payload = {
                "limitation_id": limitation_id,
                "statement": item.strip(),
                "source_type": "move_event",
                "source_id": None,
                "evidence_ref": None,
                "tool_run_id": None,
            }
            out.append(
                {
                    "candidate_id": f"limitation::{limitation_id}",
                    "slice_type": "limitations",
                    "evidence_ref": None,
                    "approx_tokens": _estimate_payload_tokens(payload),
                    "summary": summary,
                    "title": summary,
                    "payload": payload,
                }
            )
    return out


def _allocate_slice_budgets(
    *,
    deps: ContextPackAssemblyDeps,
    move_type: MoveType,
    work_mode: str,
    token_budget: int,
    slices: list[dict[str, Any]],
    framing: dict[str, Any] | None,
    issues: list[dict[str, Any]],
) -> tuple[dict[str, int], list[str], str | None]:
    if not slices:
        return {}, [], None
    sys = (
        "You are the ContextPack allocator for The Planner's Assistant.\n"
        "Allocate a token budget across slices for the move.\n"
        "Return ONLY valid JSON: {\"slice_budgets\": {slice_type: tokens...}, \"notes\": string}.\n"
        "Rules:\n"
        "- Sum of slice budgets must be <= total_token_budget.\n"
        "- Prioritize slices most relevant to the move and issues.\n"
        "- If a slice has zero candidates, allocate 0.\n"
    )
    payload = {
        "move_type": move_type,
        "work_mode": work_mode,
        "total_token_budget": token_budget,
        "framing": framing or {},
        "issues": [{"issue_id": i.get("issue_id"), "title": i.get("title")} for i in issues if isinstance(i, dict)],
        "slices": [
            {
                "slice_type": s.get("slice_type"),
                "candidate_count": s.get("candidate_count"),
                "candidate_token_estimate": s.get("candidate_token_estimate"),
            }
            for s in slices
        ],
    }
    obj, tool_run_id, errs = deps.llm_structured_sync(
        prompt_id="context_pack.allocate_budget",
        prompt_version=1,
        prompt_name="ContextPack budget allocation",
        purpose="Allocate a token budget across context pack slices.",
        system_template=sys,
        user_payload=payload,
        output_schema_ref="schemas/ContextPackBudgetAllocation.schema.json",
    )
    if not isinstance(obj, dict):
        return {}, errs, tool_run_id
    budgets = obj.get("slice_budgets") if isinstance(obj.get("slice_budgets"), dict) else {}
    out: dict[str, int] = {}
    total = 0
    for key, value in budgets.items():
        if not isinstance(key, str):
            continue
        if not isinstance(value, int):
            continue
        if value <= 0:
            continue
        out[key] = value
        total += value
    if total > token_budget:
        scale = token_budget / total
        out = {k: max(0, int(v * scale)) for k, v in out.items()}
    return out, errs, tool_run_id


def _select_slice_with_llm(
    *,
    deps: ContextPackAssemblyDeps,
    move_type: MoveType,
    work_mode: str,
    slice_type: str,
    candidates: list[dict[str, Any]],
    token_budget: int,
    framing: dict[str, Any] | None,
    issues: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]], list[str], str | None]:
    if not candidates or token_budget <= 0:
        return [], [], [], None
    sys = (
        "You are selecting context items for a planning judgement move.\n"
        "Return ONLY valid JSON: {\"selected_candidate_ids\": [...], \"deliberate_omissions\": [...], \"notes\": string}.\n"
        "Rules:\n"
        "- Only choose candidate_ids provided.\n"
        "- Respect the token_budget (sum of approx_tokens for selected items).\n"
        "- Prefer diversity across documents and modalities where relevant.\n"
        "- Do not invent citations.\n"
    )
    payload = {
        "move_type": move_type,
        "work_mode": work_mode,
        "slice_type": slice_type,
        "token_budget": token_budget,
        "framing": framing or {},
        "issues": [{"issue_id": i.get("issue_id"), "title": i.get("title")} for i in issues if isinstance(i, dict)],
        "candidates": [
            {
                "candidate_id": c.get("candidate_id"),
                "title": c.get("title"),
                "summary": c.get("summary"),
                "approx_tokens": c.get("approx_tokens"),
                "evidence_ref": c.get("evidence_ref"),
            }
            for c in candidates
        ],
    }
    obj, tool_run_id, errs = deps.llm_structured_sync(
        prompt_id="context_pack.select_slice",
        prompt_version=1,
        prompt_name="ContextPack slice selection",
        purpose="Select relevant context items within a token budget.",
        system_template=sys,
        user_payload=payload,
        output_schema_ref="schemas/ContextPackSelection.schema.json",
    )
    if not isinstance(obj, dict):
        return [], [], errs, tool_run_id
    selected_ids = obj.get("selected_candidate_ids") if isinstance(obj.get("selected_candidate_ids"), list) else []
    selected_ids = [cid for cid in selected_ids if isinstance(cid, str)]
    omissions = obj.get("deliberate_omissions") if isinstance(obj.get("deliberate_omissions"), list) else []

    selected_ids = [cid for cid in selected_ids if cid in {c.get("candidate_id") for c in candidates}]

    # Enforce token budget using candidate estimates.
    selected: list[str] = []
    total_tokens = 0
    token_by_id = {c.get("candidate_id"): int(c.get("approx_tokens") or 0) for c in candidates}
    for cid in selected_ids:
        cost = token_by_id.get(cid, 0)
        if total_tokens + cost > token_budget:
            continue
        selected.append(cid)
        total_tokens += cost

    return selected, omissions, errs, tool_run_id


def build_context_pack_sync(
    *,
    deps: ContextPackAssemblyDeps,
    run_id: str,
    move_type: MoveType,
    work_mode: str,
    authority_id: str | None,
    plan_cycle_id: str | None,
    plan_project_id: str | None,
    scenario_id: str | None,
    application_id: str | None,
    framing: dict[str, Any] | None,
    issues: list[dict[str, Any]],
    token_budget: int | None,
) -> dict[str, Any]:
    selector = _resolve_context_selector(work_mode=work_mode, move_type=move_type)
    if not selector:
        raise RuntimeError(f"context_selector_not_found:{work_mode}:{move_type}")
    selection_policy = _load_context_selector_registry().get("selection_policy") if isinstance(_load_context_selector_registry(), dict) else {}
    default_budget = selection_policy.get("context_budget_tokens")
    budget = int(token_budget or default_budget or 128000)

    gate_status = _gate_slice_availability(
        deps=deps,
        authority_id=authority_id,
        plan_cycle_id=plan_cycle_id,
        plan_project_id=plan_project_id,
        application_id=application_id,
    )

    slices = selector.get("slices") if isinstance(selector.get("slices"), list) else []
    active_slices = [s for s in slices if isinstance(s, dict) and _apply_gating(s, gate_status)]

    candidates: dict[str, list[dict[str, Any]]] = {}
    for slice_entry in active_slices:
        slice_type = slice_entry.get("slice_type")
        if not isinstance(slice_type, str):
            continue
        if slice_type == "policy_clauses":
            candidates[slice_type] = _policy_clause_candidates(
                deps=deps,
                authority_id=authority_id,
                plan_cycle_id=plan_cycle_id,
            )
        elif slice_type == "evidence_atoms":
            candidates[slice_type] = _evidence_atom_candidates(deps=deps, run_id=run_id)
        elif slice_type == "visual_assets":
            candidates[slice_type] = _visual_asset_candidates(
                deps=deps,
                authority_id=authority_id,
                plan_cycle_id=plan_cycle_id,
            )
        elif slice_type == "spatial_features":
            candidates[slice_type] = _spatial_feature_candidates(deps=deps, authority_id=authority_id)
        elif slice_type == "consultations":
            candidates[slice_type] = _consultation_candidates(deps=deps, plan_project_id=plan_project_id)
        elif slice_type == "decisions":
            candidates[slice_type] = _decision_candidates(deps=deps, application_id=application_id)
        elif slice_type == "advice_cards":
            candidates[slice_type] = _advice_card_candidates(
                deps=deps,
                authority_id=authority_id,
                plan_cycle_id=plan_cycle_id,
            )
        elif slice_type == "assumptions":
            candidates[slice_type] = _assumption_candidates(deps=deps, run_id=run_id)
        elif slice_type == "limitations":
            candidates[slice_type] = _limitation_candidates(deps=deps, run_id=run_id)

    slice_budget_inputs = []
    for slice_type, items in candidates.items():
        slice_budget_inputs.append(
            {
                "slice_type": slice_type,
                "candidate_count": len(items),
                "candidate_token_estimate": sum(int(i.get("approx_tokens") or 0) for i in items),
            }
        )

    slice_budgets, budget_errs, budget_tool_run_id = _allocate_slice_budgets(
        deps=deps,
        move_type=move_type,
        work_mode=work_mode,
        token_budget=budget,
        slices=slice_budget_inputs,
        framing=framing,
        issues=issues,
    )
    if not slice_budgets:
        # If allocation fails, split the budget evenly across available slices.
        active = [k for k, v in candidates.items() if v]
        if active:
            per = max(1, budget // len(active))
            slice_budgets = {k: per for k in active}

    selection_tool_runs: list[str] = []
    slice_omissions: list[dict[str, Any]] = []
    selected_payloads: dict[str, list[dict[str, Any]]] = {}
    for slice_type, items in candidates.items():
        slice_budget = slice_budgets.get(slice_type, 0)
        selected_ids, omissions, errs, tool_run_id = _select_slice_with_llm(
            deps=deps,
            move_type=move_type,
            work_mode=work_mode,
            slice_type=slice_type,
            candidates=items,
            token_budget=slice_budget,
            framing=framing,
            issues=issues,
        )
        if errs:
            raise RuntimeError(f"context_pack_selection_failed:{slice_type}:{';'.join(errs)}")
        if tool_run_id:
            selection_tool_runs.append(tool_run_id)
        if isinstance(omissions, list):
            for omission in omissions:
                if not isinstance(omission, dict):
                    continue
                omission["slice_type"] = slice_type
                slice_omissions.append(omission)
        selected = {c.get("candidate_id"): c for c in items}
        selected_payloads[slice_type] = [selected[cid]["payload"] for cid in selected_ids if cid in selected]

    context_pack_id = str(uuid4())
    pack = {
        "context_pack_id": context_pack_id,
        "run_id": run_id,
        "move_type": move_type,
        "work_mode": work_mode,
        "authority_id": authority_id,
        "plan_cycle_id": plan_cycle_id,
        "plan_project_id": plan_project_id,
        "scenario_id": scenario_id,
        "application_id": application_id,
        "selector_id": selector.get("selector_id"),
        "created_at": deps.utc_now_iso(),
        "slices": {
            "policy_clauses": selected_payloads.get("policy_clauses", []),
            "evidence_atoms": selected_payloads.get("evidence_atoms", []),
            "visual_assets": selected_payloads.get("visual_assets", []),
            "spatial_features": selected_payloads.get("spatial_features", []),
            "consultations": selected_payloads.get("consultations", []),
            "decisions": selected_payloads.get("decisions", []),
            "advice_cards": selected_payloads.get("advice_cards", []),
            "assumptions": selected_payloads.get("assumptions", []),
            "limitations": selected_payloads.get("limitations", []),
        },
    }

    tool_run_id = str(uuid4())
    deps.db_execute(
        """
        INSERT INTO tool_runs (id, run_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note)
        VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
        """,
        (
            tool_run_id,
            run_id,
            "context_pack_assembly",
            json.dumps(
                {
                    "selector_id": selector.get("selector_id"),
                    "move_type": move_type,
                    "work_mode": work_mode,
                    "token_budget": budget,
                    "slice_budgets": slice_budgets,
                    "selection_tool_runs": selection_tool_runs,
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "ok": True,
                    "budget_tool_run_id": budget_tool_run_id,
                    "budget_errors": budget_errs,
                    "slice_omissions": slice_omissions,
                },
                ensure_ascii=False,
            ),
            "success",
            deps.utc_now(),
            deps.utc_now(),
            "medium",
            "ContextPack selection is LLM-assisted and bounded by a token budget; review omissions where critical.",
        ),
    )

    deps.db_execute(
        """
        INSERT INTO context_packs (
          id, run_id, move_type, work_mode, authority_id, plan_cycle_id, plan_project_id,
          scenario_id, application_id, selector_id, pack_jsonb, tool_run_id, created_at
        )
        VALUES (%s, %s::uuid, %s, %s, %s, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, %s::uuid, %s)
        """,
        (
            context_pack_id,
            run_id,
            move_type,
            work_mode,
            authority_id,
            plan_cycle_id,
            plan_project_id,
            scenario_id,
            application_id,
            selector.get("selector_id"),
            json.dumps(pack, ensure_ascii=False),
            tool_run_id,
            deps.utc_now(),
        ),
    )

    return pack
