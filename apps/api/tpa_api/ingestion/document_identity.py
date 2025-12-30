from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from tpa_api.db import _db_execute
from tpa_api.prompting import _llm_structured_sync
from tpa_api.time_utils import _utc_now, _utc_now_iso


def _infer_source_kind(filename: str | None, content_type: str | None) -> str:
    if isinstance(content_type, str):
        lowered = content_type.lower()
        if "pdf" in lowered:
            return "PDF"
        if "word" in lowered or "docx" in lowered:
            return "DOCX"
        if "html" in lowered:
            return "HTML"
        if "image" in lowered:
            return "IMAGE"
    if not isinstance(filename, str):
        return "OTHER"
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "PDF"
    if ext in {".doc", ".docx"}:
        return "DOCX"
    if ext in {".html", ".htm"}:
        return "HTML"
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        return "IMAGE"
    return "OTHER"


def _normalize_status_confidence(value: str | None) -> str:
    if not isinstance(value, str):
        return "LOW"
    upper = value.strip().upper()
    if upper in {"HIGH", "MEDIUM", "LOW"}:
        return upper
    return "LOW"


def _status_confidence_at_least(value: str, minimum: str) -> bool:
    order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    return order.get(value, 1) >= order.get(minimum, 2)


def _build_identity_evidence_options(
    *,
    document_id: str,
    block_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for block in block_rows:
        block_id = block.get("block_id")
        page_number = block.get("page_number")
        text = block.get("text")
        if not isinstance(block_id, str) or not isinstance(page_number, int):
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        locator_value = f"p{page_number}-{block_id}"
        options.append(
            {
                "document_id": document_id,
                "locator_type": "paragraph",
                "locator_value": locator_value,
                "excerpt": text,
            }
        )
    return options


def _filter_identity_evidence(
    evidence: Any,
    *,
    document_id: str,
    options_by_key: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(evidence, list):
        return []
    filtered: list[dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        locator_type = item.get("locator_type")
        locator_value = item.get("locator_value")
        if not isinstance(locator_type, str) or not isinstance(locator_value, str):
            continue
        key = (locator_type, locator_value)
        option = options_by_key.get(key)
        if not option:
            continue
        filtered.append(
            {
                "document_id": document_id,
                "locator_type": locator_type,
                "locator_value": locator_value,
                "excerpt": option.get("excerpt") or "",
            }
        )
    return filtered


def _apply_document_weight_rules(
    *,
    identity: dict[str, Any],
    status: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    warnings: list[str] = []
    applied_rules: list[str] = []
    doc_family = identity.get("document_family") if isinstance(identity.get("document_family"), str) else "UNKNOWN"
    status_claim = status.get("status_claim") if isinstance(status.get("status_claim"), str) else "NOT_STATED"
    status_confidence = _normalize_status_confidence(status.get("status_confidence"))
    status_evidence = status.get("status_evidence") if isinstance(status.get("status_evidence"), list) else []
    status_evidence_missing = len(status_evidence) == 0
    status_claim_raw = status_claim

    if status_claim in {"ADOPTED", "MADE", "APPROVED"} and status_evidence_missing:
        status["status_claim"] = "NOT_STATED"
        status["status_confidence"] = "LOW"
        status["status_note"] = "Status claim lacked explicit evidence; downgraded to NOT_STATED."
        status_claim = "NOT_STATED"
        status_confidence = "LOW"
        warnings.append("NO_STATUS_EVIDENCE")
        applied_rules.append("R8_NO_EVIDENCE_DEGRADE")

    weight_class = "UNKNOWN"
    legal_assertion_level = "ASSERT_NONE"
    phrasing_guidance = "SAY_SYSTEM_CLASSIFIES_FOR_NAVIGATION_ONLY"
    basis: list[dict[str, Any]] = []

    if (
        doc_family in {"LOCAL_PLAN_DPD", "SPATIAL_DEVELOPMENT_STRATEGY", "NEIGHBOURHOOD_PLAN"}
        and status_claim in {"ADOPTED", "MADE", "APPROVED"}
        and _status_confidence_at_least(status_confidence, "MEDIUM")
        and not status_evidence_missing
    ):
        weight_class = "DEVELOPMENT_PLAN"
        legal_assertion_level = "ASSERT_CLAIMED_BY_DOCUMENT"
        phrasing_guidance = "SAY_DOCUMENT_PRESENTS_ITSELF_AS"
        applied_rules.append("R1_DEV_PLAN_EXPLICIT")
    elif (
        doc_family in {"LOCAL_PLAN_DPD", "SPATIAL_DEVELOPMENT_STRATEGY", "NEIGHBOURHOOD_PLAN"}
        and status_claim
        in {
            "REGULATION_18",
            "REGULATION_19",
            "PUBLICATION_DRAFT",
            "SUBMISSION",
            "EXAMINATION",
            "PROPOSED_MODIFICATIONS",
            "CONSULTATION_DRAFT",
        }
        and not status_evidence_missing
    ):
        weight_class = "EMERGING_POLICY"
        legal_assertion_level = "ASSERT_CLAIMED_BY_DOCUMENT"
        phrasing_guidance = "SAY_DOCUMENT_PRESENTS_ITSELF_AS"
        applied_rules.append("R2_EMERGING_POLICY_EXPLICIT")
    elif doc_family in {"SPD", "DESIGN_CODE"} and status_claim in {"ADOPTED", "APPROVED"} and not status_evidence_missing:
        weight_class = "SPD_GUIDANCE"
        legal_assertion_level = "ASSERT_CLAIMED_BY_DOCUMENT"
        phrasing_guidance = "SAY_DOCUMENT_PRESENTS_ITSELF_AS"
        applied_rules.append("R3_SPD_EXPLICIT")
    elif doc_family in {"NPPF_PPG_NATIONAL_POLICY"}:
        weight_class = "MATERIAL_CONSIDERATION"
        applied_rules.append("R4_NATIONAL_POLICY")
    elif doc_family in {
        "EVIDENCE_BASE",
        "TECHNICAL_REPORT",
        "CONSULTEE_RESPONSE",
        "PUBLIC_REPRESENTATION",
        "OFFICER_REPORT",
        "DECISION_NOTICE",
        "COMMITTEE_MINUTES",
        "APPEAL_DECISION",
        "S106_HEADS_OR_AGREEMENT",
        "APPLICANT_STATEMENT",
        "DRAWING_SET",
    }:
        weight_class = "MATERIAL_CONSIDERATION"
        applied_rules.append("R5_MATERIAL_CONSIDERATION_DEFAULT")
    elif doc_family in {"MARKETING_OR_ILLUSTRATIVE"}:
        weight_class = "ILLUSTRATIVE_LOW_WEIGHT"
        applied_rules.append("R6_ILLUSTRATIVE_LOW_WEIGHT")

    if weight_class == "UNKNOWN":
        plan_families = {"LOCAL_PLAN_DPD", "SPATIAL_DEVELOPMENT_STRATEGY", "NEIGHBOURHOOD_PLAN"}
        emerging_statuses = {
            "REGULATION_18",
            "REGULATION_19",
            "PUBLICATION_DRAFT",
            "SUBMISSION",
            "EXAMINATION",
            "PROPOSED_MODIFICATIONS",
            "CONSULTATION_DRAFT",
        }
        adopted_statuses = {"ADOPTED", "MADE", "APPROVED"}
        if doc_family in plan_families:
            if status_claim_raw in adopted_statuses:
                weight_class = "DEVELOPMENT_PLAN"
                applied_rules.append("R10_IMPLICIT_DEV_PLAN")
            elif status_claim_raw in emerging_statuses:
                weight_class = "EMERGING_POLICY"
                applied_rules.append("R11_IMPLICIT_EMERGING_POLICY")
            else:
                weight_class = "EMERGING_POLICY"
                applied_rules.append("R12_PLAN_FAMILY_ONLY")
            legal_assertion_level = "ASSERT_NONE"
            phrasing_guidance = "SAY_SYSTEM_CLASSIFIES_FOR_NAVIGATION_ONLY"
            if "LOW_PROVENANCE" not in warnings:
                warnings.append("LOW_PROVENANCE")
        elif doc_family in {"SPD", "DESIGN_CODE"}:
            weight_class = "SPD_GUIDANCE"
            applied_rules.append("R13_SPD_FAMILY_ONLY")
            legal_assertion_level = "ASSERT_NONE"
            phrasing_guidance = "SAY_SYSTEM_CLASSIFIES_FOR_NAVIGATION_ONLY"
            if "LOW_PROVENANCE" not in warnings:
                warnings.append("LOW_PROVENANCE")

    if status_claim in {"SUPERSEDED", "WITHDRAWN"}:
        warnings.append("TIME_SENSITIVE_STATUS")
        applied_rules.append("R7_SUPERSEDED_OR_WITHDRAWN_WARNING")

    basis_note: str | None = None
    basis_type: str | None = None
    if weight_class != "UNKNOWN" and applied_rules:
        last_rule = applied_rules[-1]
        if last_rule in {"R10_IMPLICIT_DEV_PLAN", "R11_IMPLICIT_EMERGING_POLICY"}:
            basis_type = "DERIVED_RULE"
            basis_note = "Status implied from document signals; explicit evidence missing."
        elif last_rule in {"R12_PLAN_FAMILY_ONLY", "R13_SPD_FAMILY_ONLY"}:
            basis_type = "DOCUMENT_FAMILY_ONLY"
            basis_note = "Document family indicates category; status not evidenced."

    if status_evidence and weight_class != "UNKNOWN":
        basis.append(
            {
                "basis_type": "EXPLICIT_IN_DOCUMENT",
                "evidence": status_evidence,
                "rule_id": applied_rules[-1] if applied_rules else None,
            }
        )
    elif basis_type:
        basis.append(
            {
                "basis_type": basis_type,
                "evidence": identity.get("identity_evidence") if isinstance(identity.get("identity_evidence"), list) else [],
                "rule_id": applied_rules[-1] if applied_rules else None,
                "note": basis_note,
            }
        )
    elif identity.get("identity_evidence"):
        basis.append(
            {
                "basis_type": "DOCUMENT_FAMILY_ONLY",
                "evidence": identity.get("identity_evidence"),
                "rule_id": applied_rules[-1] if applied_rules else None,
            }
        )

    weight = {
        "document_id": identity.get("document_id"),
        "weight_class": weight_class,
        "classification_basis": basis,
        "legal_assertion_level": legal_assertion_level,
        "phrasing_guidance": phrasing_guidance,
        "warnings": warnings,
    }
    return weight, status, applied_rules


def _extract_document_identity_status(
    *,
    ingest_batch_id: str | None,
    run_id: str | None,
    document_id: str,
    title: str,
    filename: str | None,
    content_type: str | None,
    block_rows: list[dict[str, Any]],
    evidence_ref_map: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    evidence_options = _build_identity_evidence_options(document_id=document_id, block_rows=block_rows)
    options_by_key = {
        (opt.get("locator_type"), opt.get("locator_value")): opt
        for opt in evidence_options
        if isinstance(opt.get("locator_type"), str) and isinstance(opt.get("locator_value"), str)
    }
    source_kind = _infer_source_kind(filename, content_type)
    system_template = (
        "You are a planning document classifier. Return ONLY valid JSON.\n"
        "Output shape:\n"
        "{\n"
        '  "identity": {\n'
        '    "document_id": "string",\n'
        '    "title": "string",\n'
        '    "author": "string",\n'
        '    "publisher": "string",\n'
        '    "jurisdiction": "UK-England|UK-Scotland|UK-Wales|UK-NI|Unknown",\n'
        '    "lpa_name": "string",\n'
        '    "lpa_code": "string",\n'
        '    "document_family": "LOCAL_PLAN_DPD|SPATIAL_DEVELOPMENT_STRATEGY|NEIGHBOURHOOD_PLAN|SPD|NPPF_PPG_NATIONAL_POLICY|EVIDENCE_BASE|TECHNICAL_REPORT|DESIGN_CODE|APPLICANT_STATEMENT|DRAWING_SET|CONSULTEE_RESPONSE|PUBLIC_REPRESENTATION|OFFICER_REPORT|DECISION_NOTICE|COMMITTEE_MINUTES|APPEAL_DECISION|S106_HEADS_OR_AGREEMENT|MARKETING_OR_ILLUSTRATIVE|UNKNOWN",\n'
        '    "source_kind": "PDF|DOCX|HTML|EMAIL|GIS|IMAGE|OTHER",\n'
        '    "version_label": "string",\n'
        '    "publication_date": "YYYY-MM-DD",\n'
        '    "revision_date": "YYYY-MM-DD",\n'
        '    "identity_evidence": [ {"document_id": "string", "locator_type": "paragraph", "locator_value": "string", "excerpt": "string"} ],\n'
        '    "notes": "string"\n'
        "  },\n"
        '  "status": {\n'
        '    "document_id": "string",\n'
        '    "status_claim": "ADOPTED|MADE|APPROVED|PUBLICATION_DRAFT|REGULATION_18|REGULATION_19|SUBMISSION|EXAMINATION|PROPOSED_MODIFICATIONS|CONSULTATION_DRAFT|WITHDRAWN|SUPERSEDED|NOT_STATED",\n'
        '    "status_confidence": "HIGH|MEDIUM|LOW",\n'
        '    "status_evidence": [ {"document_id": "string", "locator_type": "paragraph", "locator_value": "string", "excerpt": "string"} ],\n'
        '    "checked_at": "YYYY-MM-DDTHH:MM:SSZ",\n'
        '    "status_note": "string"\n'
        "  }\n"
        "}\n"
        "Rules:\n"
        "- Only use evidence refs from evidence_options.\n"
        "- Use locator_type \"paragraph\".\n"
        "- If status is not stated, set status_claim to NOT_STATED and status_confidence LOW.\n"
    )
    payload = {
        "document_id": document_id,
        "title": title,
        "source_kind_hint": source_kind,
        "evidence_options": evidence_options,
    }
    obj, tool_run_id, errs = _llm_structured_sync(
        prompt_id="document_identity_status_v1",
        prompt_version=1,
        prompt_name="Document identity/status classifier",
        purpose="Classify document identity, status, and planning weight with explicit evidence.",
        system_template=system_template,
        user_payload=payload,
        output_schema_ref="schemas/DocumentIdentityStatusBundle.schema.json",
        ingest_batch_id=ingest_batch_id,
        run_id=run_id,
    )
    if not isinstance(obj, dict):
        return None, tool_run_id, errs

    identity = obj.get("identity") if isinstance(obj.get("identity"), dict) else {}
    status = obj.get("status") if isinstance(obj.get("status"), dict) else {}

    identity.setdefault("document_id", document_id)
    if not identity.get("title"):
        identity["title"] = title
    identity.setdefault("source_kind", source_kind)
    identity.setdefault("document_family", "UNKNOWN")
    identity.setdefault("jurisdiction", "Unknown")
    identity_evidence = _filter_identity_evidence(
        identity.get("identity_evidence"),
        document_id=document_id,
        options_by_key=options_by_key,
    )
    identity["identity_evidence"] = identity_evidence

    status.setdefault("document_id", document_id)
    status.setdefault("status_claim", "NOT_STATED")
    status["status_confidence"] = _normalize_status_confidence(status.get("status_confidence"))
    status_evidence = _filter_identity_evidence(
        status.get("status_evidence"),
        document_id=document_id,
        options_by_key=options_by_key,
    )
    status["status_evidence"] = status_evidence
    status["checked_at"] = _utc_now_iso()

    weight, status, rules_applied = _apply_document_weight_rules(identity=identity, status=status)
    bundle = {"identity": identity, "status": status, "weight": weight}

    identity_ref_ids: list[str] = []
    status_ref_ids: list[str] = []
    if evidence_ref_map:
        for ev in identity_evidence:
            locator_value = ev.get("locator_value")
            if isinstance(locator_value, str):
                ref_id = evidence_ref_map.get(locator_value)
                if ref_id:
                    identity_ref_ids.append(ref_id)
        for ev in status_evidence:
            locator_value = ev.get("locator_value")
            if isinstance(locator_value, str):
                ref_id = evidence_ref_map.get(locator_value)
                if ref_id:
                    status_ref_ids.append(ref_id)

    _db_execute(
        """
        INSERT INTO document_identity_status (
          id, document_id, run_id, identity_jsonb, status_jsonb, weight_jsonb, metadata_jsonb, tool_run_id, created_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::uuid, %s)
        """,
        (
            str(uuid4()),
            document_id,
            run_id,
            json.dumps(identity, ensure_ascii=False),
            json.dumps(status, ensure_ascii=False),
            json.dumps(weight, ensure_ascii=False),
            json.dumps(
                {
                    "rules_applied": rules_applied,
                    "identity_evidence_ref_ids": identity_ref_ids,
                    "status_evidence_ref_ids": status_ref_ids,
                },
                ensure_ascii=False,
            ),
            tool_run_id,
            _utc_now(),
        ),
    )
    _db_execute(
        """
        UPDATE documents
        SET document_status = %s,
            weight_hint = %s,
            metadata = metadata || %s::jsonb
        WHERE id = %s::uuid
        """,
        (
            status.get("status_claim"),
            weight.get("weight_class"),
            json.dumps(
                {
                    "document_family": identity.get("document_family"),
                    "status_confidence": status.get("status_confidence"),
                },
                ensure_ascii=False,
            ),
            document_id,
        ),
    )

    return bundle, tool_run_id, errs
