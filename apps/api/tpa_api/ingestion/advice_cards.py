from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from tpa_api.db import _db_execute, _db_fetch_all, _db_fetch_one
from tpa_api.evidence import _ensure_evidence_ref_row
from tpa_api.prompting import _llm_structured_sync
from tpa_api.spec_io import _read_yaml, _spec_root
from tpa_api.time_utils import _utc_now


def _load_good_practice_cards() -> dict[str, Any]:
    path = (_spec_root() / "governance" / "GOOD_PRACTICE_CARDS.yaml").resolve()
    try:
        data = _read_yaml(Path(path))
    except Exception:  # noqa: BLE001
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data


def _family_to_applies_to(document_family: str | None) -> list[str]:
    applies = ["plan_making"]
    if document_family in {"LOCAL_PLAN_DPD", "SPATIAL_DEVELOPMENT_STRATEGY", "NEIGHBOURHOOD_PLAN"}:
        applies.append("local_plan")
    if document_family == "SPD":
        applies.append("spd")
    if document_family == "DESIGN_CODE":
        applies.append("design_code")
    if document_family in {"OFFICER_REPORT", "DECISION_NOTICE", "APPLICANT_STATEMENT"}:
        applies.append("dm")
    return applies


def _select_candidate_cards(cards: list[dict[str, Any]], applies_to: list[str]) -> list[dict[str, Any]]:
    out = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        card_applies = card.get("applies_to")
        if not isinstance(card_applies, list):
            continue
        if any(a in card_applies for a in applies_to):
            out.append(card)
    return out


def _document_identity_status(document_id: str) -> dict[str, Any] | None:
    row = _db_fetch_one(
        """
        SELECT identity_jsonb, status_jsonb, weight_jsonb
        FROM document_identity_status
        WHERE document_id = %s::uuid
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (document_id,),
    )
    if not isinstance(row, dict):
        return None
    return {
        "identity": row.get("identity_jsonb"),
        "status": row.get("status_jsonb"),
        "weight": row.get("weight_jsonb"),
    }


def _existing_card_ids(*, scope_id: str, scope_type: str) -> set[str]:
    rows = _db_fetch_all(
        """
        SELECT card_id
        FROM advice_card_instances
        WHERE scope_id = %s::uuid AND scope_type = %s AND status = 'active'
        """,
        (scope_id, scope_type),
    )
    return {str(r.get("card_id")) for r in rows if isinstance(r, dict) and r.get("card_id")}


def _persist_card_instance(
    *,
    card_id: str,
    card_version: str | None,
    scope_type: str,
    scope_id: str,
    trigger_cues: list[str],
    evidence_refs: list[str],
    tool_run_id: str | None,
    notes: str | None,
) -> None:
    instance_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO advice_card_instances (
          id, card_id, card_version, scope_type, scope_id, status,
          trigger_cues_jsonb, evidence_refs_jsonb, tool_run_id, created_at, notes
        )
        VALUES (%s, %s, %s, %s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s::uuid, %s, %s)
        """,
        (
            instance_id,
            card_id,
            card_version,
            scope_type,
            scope_id,
            "active",
            json.dumps(trigger_cues, ensure_ascii=False),
            json.dumps(evidence_refs, ensure_ascii=False),
            tool_run_id,
            _utc_now(),
            notes,
        ),
    )


def enrich_advice_cards_for_documents(
    *,
    authority_id: str,
    plan_cycle_id: str | None,
    run_id: str | None = None,
) -> dict[str, Any]:
    cards_catalogue = _load_good_practice_cards()
    cards = cards_catalogue.get("cards") if isinstance(cards_catalogue, dict) else []
    if not isinstance(cards, list):
        cards = []

    docs = _db_fetch_all(
        """
        SELECT id, document_status, weight_hint, metadata
        FROM documents
        WHERE authority_id = %s
          AND is_active = true
          AND (%s::uuid IS NULL OR plan_cycle_id = %s::uuid)
        ORDER BY created_at ASC
        """,
        (authority_id, plan_cycle_id, plan_cycle_id),
    )

    inserted = 0
    errors: list[str] = []

    for doc in docs:
        document_id = str(doc.get("id") or "")
        if not document_id:
            continue
        existing = _existing_card_ids(scope_id=document_id, scope_type="document")
        identity_bundle = _document_identity_status(document_id)
        document_family = None
        if isinstance(identity_bundle, dict):
            identity = identity_bundle.get("identity") if isinstance(identity_bundle.get("identity"), dict) else {}
            document_family = identity.get("document_family") if isinstance(identity.get("document_family"), str) else None

        applies_to = _family_to_applies_to(document_family)
        candidate_cards = _select_candidate_cards(cards, applies_to)
        if not candidate_cards:
            continue

        doc_meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        payload = {
            "document": {
                "document_id": document_id,
                "title": doc_meta.get("title"),
                "document_status": doc.get("document_status"),
                "weight_hint": doc.get("weight_hint"),
                "document_family": document_family,
                "identity_bundle": identity_bundle or {},
            },
            "candidate_cards": [
                {
                    "card_id": c.get("card_id"),
                    "title": c.get("title"),
                    "type": c.get("type"),
                    "basis": c.get("basis"),
                    "priority": c.get("priority"),
                    "applies_at": c.get("applies_at"),
                    "dimensions": c.get("dimensions"),
                    "trigger_cues": c.get("trigger_cues"),
                    "prompt": c.get("prompt"),
                }
                for c in candidate_cards
                if isinstance(c, dict)
            ],
        }

        sys = (
            "You are matching good-practice Advice Cards to a planning document.\n"
            "Return ONLY valid JSON: {\"selected_cards\": [{\"card_id\": \"...\", \"trigger_cues\": [...], \"evidence_refs\": [...], \"notes\": \"...\"}]}.\n"
            "Rules:\n"
            "- Only choose card_id values from the candidate list.\n"
            "- Use trigger_cues to explain why the card applies.\n"
            "- evidence_refs must be provided only if they are supplied in the document bundle; otherwise leave empty.\n"
            "- Do not invent policy outcomes.\n"
        )

        obj, tool_run_id, errs = _llm_structured_sync(
            prompt_id="advice_cards.match_document",
            prompt_version=1,
            prompt_name="Advice card matching (document)",
            purpose="Select advisory good-practice prompts for a document.",
            system_template=sys,
            user_payload=payload,
            output_schema_ref="schemas/AdviceCardMatch.schema.json",
            run_id=run_id,
            ingest_batch_id=None,
        )
        if errs:
            errors.extend([f"advice_cards:{document_id}:{err}" for err in errs])
        if not isinstance(obj, dict):
            continue

        selections = obj.get("selected_cards") if isinstance(obj.get("selected_cards"), list) else []
        for sel in selections:
            if not isinstance(sel, dict):
                continue
            card_id = sel.get("card_id")
            if not isinstance(card_id, str) or card_id in existing:
                continue
            trigger_cues = sel.get("trigger_cues") if isinstance(sel.get("trigger_cues"), list) else []
            trigger_cues = [c for c in trigger_cues if isinstance(c, str)][:12]
            evidence_refs = sel.get("evidence_refs") if isinstance(sel.get("evidence_refs"), list) else []
            evidence_refs = [e for e in evidence_refs if isinstance(e, str) and "::" in e][:8]
            for evidence_ref in evidence_refs:
                _ensure_evidence_ref_row(evidence_ref)
            notes = sel.get("notes") if isinstance(sel.get("notes"), str) else None

            _persist_card_instance(
                card_id=card_id,
                card_version=str(cards_catalogue.get("version") or "1"),
                scope_type="document",
                scope_id=document_id,
                trigger_cues=trigger_cues,
                evidence_refs=evidence_refs,
                tool_run_id=tool_run_id,
                notes=notes,
            )
            inserted += 1

    return {"inserted": inserted, "errors": errors}
