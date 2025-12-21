from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..api_utils import validate_uuid_or_400 as _validate_uuid_or_400
from ..audit import _audit_event
from ..blob_store import minio_client_or_none as _minio_client_or_none
from ..chunking import _semantic_chunk_lines
from ..db import _db_execute, _db_execute_returning, _db_fetch_all, _db_fetch_one
from ..evidence import _ensure_evidence_ref_row
from ..model_clients import _embed_texts_sync
from ..prompting import _llm_structured_sync
from ..spec_io import _read_json, _read_yaml
from ..time_utils import _utc_now
from ..vector_utils import _vector_literal


_POLICY_SPEECH_ACT_NORMATIVE_FORCE = {
    "hard_constraint",
    "presumptive_support",
    "presumptive_resistance",
    "aspirational",
    "procedural",
    "justificatory",
    "defers_to_judgement",
    "unknown",
}

_POLICY_SPEECH_ACT_STRENGTH_HINT = {"strong", "moderate", "weak", "symbolic", "unknown"}
_POLICY_SPEECH_ACT_OFFICER_SPACE = {"narrow", "medium", "wide", "unknown"}


def _normalize_policy_speech_act(
    raw: Any,
    *,
    tool_run_id: str | None,
    method: str,
) -> dict[str, Any]:
    """
    Normalise a PolicySpeechAct payload from an LLM instrument output.

    We do not attempt deterministic classification here; we only validate and clamp to the
    ontology values so downstream code can rely on shape.
    """
    obj = raw if isinstance(raw, dict) else {}
    normative_force = obj.get("normative_force") if isinstance(obj.get("normative_force"), str) else "unknown"
    if normative_force not in _POLICY_SPEECH_ACT_NORMATIVE_FORCE:
        normative_force = "unknown"

    strength_hint = obj.get("strength_hint") if isinstance(obj.get("strength_hint"), str) else "unknown"
    if strength_hint not in _POLICY_SPEECH_ACT_STRENGTH_HINT:
        strength_hint = "unknown"

    officer_space = (
        obj.get("officer_interpretation_space")
        if isinstance(obj.get("officer_interpretation_space"), str)
        else "unknown"
    )
    if officer_space not in _POLICY_SPEECH_ACT_OFFICER_SPACE:
        officer_space = "unknown"

    ambiguity_flags = obj.get("ambiguity_flags") if isinstance(obj.get("ambiguity_flags"), list) else []
    ambiguity_flags = [a for a in ambiguity_flags if isinstance(a, str)][:20]

    key_terms = obj.get("key_terms") if isinstance(obj.get("key_terms"), list) else []
    key_terms = [t for t in key_terms if isinstance(t, str) and t.strip()][:20]

    limitations_text = obj.get("limitations_text") if isinstance(obj.get("limitations_text"), str) else ""
    if not limitations_text.strip():
        limitations_text = (
            "LLM modality characterisation of policy language; preserves ambiguity and is not a binding test. "
            "Verify clause boundaries and weight/status against the source plan cycle."
        )

    return {
        "normative_force": normative_force,
        "strength_hint": strength_hint,
        "ambiguity_flags": ambiguity_flags,
        "key_terms": key_terms,
        "officer_interpretation_space": officer_space,
        "method": method,
        "tool_run_id": tool_run_id,
        "limitations_text": limitations_text,
    }


def _llm_parse_policy_clauses_for_section_sync(
    *,
    ingest_batch_id: str,
    authority_id: str,
    plan_cycle_id: str,
    policy_ref: str,
    policy_title: str | None,
    source_chunks: list[dict[str, Any]],
    time_budget_seconds: float = 45.0,
) -> tuple[list[dict[str, Any]], str | None, list[str], str | None]:
    """
    LLM parse as an evidence instrument:
    parse a policy section into clause-like fragments and characterise modality without collapsing ambiguity.

    Returns (clauses, tool_run_id, errors, policy_level_notes).
    """
    # Bound input to keep calls practical on single-user OSS.
    chunks_payload: list[dict[str, Any]] = []
    allowed_refs: set[str] = set()
    total_chars = 0
    for c in source_chunks:
        ev = c.get("evidence_ref")
        if not isinstance(ev, str):
            continue
        allowed_refs.add(ev)
        text = c.get("text") if isinstance(c.get("text"), str) else ""
        text = text.strip()
        if not text:
            continue
        snippet = text[:1200]
        total_chars += len(snippet)
        if total_chars > 18000:
            break
        chunks_payload.append(
            {
                "evidence_ref": ev,
                "type": c.get("type"),
                "section_path": c.get("section_path"),
                "text": snippet,
            }
        )

    system = (
        "You are a policy parsing instrument for The Planner's Assistant.\n"
        "Goal: parse Local Plan policy language into citeable clause fragments AND characterise modality.\n"
        "Critical: DO NOT turn policy into 'requirements' or compliance tests. Do NOT decide.\n"
        "Preserve ambiguity explicitly via ambiguity_flags and 'unknown' where needed.\n\n"
        "Return ONLY valid JSON with this shape:\n"
        "{\n"
        "  \"clauses\": [\n"
        "    {\n"
        "      \"clause_ref\": string|null,\n"
        "      \"text\": string,\n"
        "      \"source_evidence_refs\": [EvidenceRef...],\n"
        "      \"speech_act\": {\n"
        "        \"normative_force\": one of [hard_constraint,presumptive_support,presumptive_resistance,aspirational,procedural,justificatory,defers_to_judgement,unknown],\n"
        "        \"strength_hint\": one of [strong,moderate,weak,symbolic,unknown],\n"
        "        \"ambiguity_flags\": [string...],\n"
        "        \"key_terms\": [string...],\n"
        "        \"officer_interpretation_space\": one of [narrow,medium,wide,unknown],\n"
        "        \"method\": \"llm_policy_clause_parse_v1\",\n"
        "        \"tool_run_id\": null,\n"
        "        \"limitations_text\": string\n"
        "      }\n"
        "    }\n"
        "  ],\n"
        "  \"policy_level_notes\": string|null\n"
        "}\n\n"
        "Citations rule: source_evidence_refs MUST be chosen only from the provided evidence_ref list; never invent citations.\n"
        "If you cannot safely bind a clause to sources, return an empty source_evidence_refs array and include an ambiguity flag like \"insufficient_source_binding\".\n"
        "Do not include markdown fences."
    )

    obj, tool_run_id, errs = _llm_structured_sync(
        prompt_id="ingest.policy_clause_parse",
        prompt_version=1,
        prompt_name="Policy clause parse + modality characterisation",
        purpose="Parse policy sections into clause fragments and characterise modality without collapsing ambiguity.",
        system_template=system,
        user_payload={
            "authority_id": authority_id,
            "plan_cycle_id": plan_cycle_id,
            "policy_ref": policy_ref,
            "policy_title": policy_title,
            "ontology_ref": "ingest/POLICY_MODALITY_ONTOLOGY.yaml",
            "source_chunks": chunks_payload,
            "max_clauses": 20,
        },
        time_budget_seconds=time_budget_seconds,
        temperature=0.6,
        max_tokens=1600,
        output_schema_ref="schemas/PolicyClauseParseResult.schema.json",
        ingest_batch_id=ingest_batch_id,
    )

    if tool_run_id is None and errs == ["llm_unconfigured"]:
        # Provide a stable tool_run envelope for auditability even when the LLM is not running.
        tool_run_id = str(uuid4())
        started = _utc_now()
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                tool_run_id,
                ingest_batch_id,
                "policy_clause_parse_unavailable",
                json.dumps(
                    {"authority_id": authority_id, "plan_cycle_id": plan_cycle_id, "policy_ref": policy_ref},
                    ensure_ascii=False,
                ),
                json.dumps({"error": "llm_unconfigured"}, ensure_ascii=False),
                "error",
                started,
                _utc_now(),
                "low",
                "Policy parsing requires an LLM instrument; start the LLM service for this profile to enable it.",
            ),
        )

    clauses_raw = obj.get("clauses") if isinstance(obj, dict) else None
    clauses: list[dict[str, Any]] = []
    if isinstance(clauses_raw, list):
        for c in clauses_raw[:20]:
            if not isinstance(c, dict):
                continue
            text = c.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            refs = c.get("source_evidence_refs")
            if not isinstance(refs, list):
                refs = []
            refs = [r for r in refs if isinstance(r, str) and r in allowed_refs][:30]
            speech_act = _normalize_policy_speech_act(c.get("speech_act"), tool_run_id=tool_run_id, method="llm_policy_clause_parse_v1")
            if not refs:
                # Preserve the fact that we could not bind to sources.
                af = set(speech_act.get("ambiguity_flags") or [])
                af.add("insufficient_source_binding")
                speech_act["ambiguity_flags"] = sorted([a for a in af if isinstance(a, str)])
            clauses.append(
                {
                    "clause_ref": c.get("clause_ref") if isinstance(c.get("clause_ref"), str) else None,
                    "text": text.strip(),
                    "source_evidence_refs": refs,
                    "speech_act": speech_act,
                }
            )

    policy_notes = obj.get("policy_level_notes") if isinstance(obj, dict) and isinstance(obj.get("policy_level_notes"), str) else None
    if not clauses:
        errs.append("policy_clause_parse_no_valid_clauses")
    return clauses, tool_run_id, errs, policy_notes


def _extract_policies_from_document_chunks(
    *,
    authority_id: str,
    plan_cycle_id: str,
    ingest_batch_id: str,
    document_id: str,
    document_title: str | None,
    plan_cycle_status: str | None,
    plan_cycle_weight_hint: str | None,
    effective_from: date | None,
    effective_to: date | None,
    embed_policy_clause_embeddings: bool = True,
) -> dict[str, Any]:
    """
    Policy extraction as an evidence instrument:
    - deterministic candidate sectioning (headings/chunks),
    - non-deterministic LLM parsing into clause fragments + modality characterisation (persisted + logged).

    Produces:
    - `policies` rows (one per detected policy heading),
    - `policy_clauses` rows (v0: derived from paragraph/bullet chunks under each policy),
    - `evidence_refs` for each clause (`policy_clause::{id}::text`),
    - a planner-legible modality characterisation per clause (speech act), preserving ambiguity,
    - optional `policy_clause_embeddings` for clause-aware hybrid retrieval.

    This is a parsing instrument, not judgement.
    """

    extraction_tool_run_id = str(uuid4())
    extraction_started = _utc_now()

    # Policy extraction is intended to be idempotent per plan cycle + document.
    # Re-running ingestion for the same authority pack should not silently duplicate policies.
    already = _db_fetch_one(
        """
        SELECT 1
        FROM policies
        WHERE plan_cycle_id = %s::uuid
          AND is_active = true
          AND metadata->>'document_id' = %s
        LIMIT 1
        """,
        (plan_cycle_id, document_id),
    )
    if already:
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, tool_name, inputs_logged, outputs_logged,
              status, started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                extraction_tool_run_id,
                ingest_batch_id,
                "extract_policy_clauses",
                json.dumps({"document_id": document_id, "document_title": document_title}, ensure_ascii=False),
                json.dumps(
                    {"skipped": True, "reason": "policies_already_extracted_for_plan_cycle_document"},
                    ensure_ascii=False,
                ),
                "success",
                extraction_started,
                _utc_now(),
                "high",
                "No-op: policies already extracted for this plan cycle + document.",
            ),
        )
        return {
            "skipped": True,
            "policies_created": 0,
            "policy_clauses_created": 0,
            "embeddings_inserted": 0,
            "tool_run_id": extraction_tool_run_id,
        }

    rows = _db_fetch_all(
        """
        SELECT
          id,
          page_number,
          type,
          text,
          section_path,
          metadata->>'evidence_ref_fragment' AS fragment_id
        FROM chunks
        WHERE document_id = %s::uuid
        ORDER BY
          page_number ASC NULLS LAST,
          (metadata->>'evidence_ref_fragment') ASC NULLS LAST
        """,
        (document_id,),
    )

    require_llm_heading = os.environ.get("TPA_POLICY_HEADING_REQUIRE_LLM", "true").strip().lower() in {"1", "true", "yes", "y"}
    policy_heading_tool_run_id: str | None = None
    policy_heading_errors: list[str] = []

    policy_head_re = re.compile(
        r"^policy\\s+(?P<ref>[A-Za-z]{0,6}\\d+[A-Za-z]?)\\b(?P<rest>.*)$",
        flags=re.IGNORECASE,
    )

    def parse_policy_heading(text: str) -> tuple[str, str | None] | None:
        s = (text or "").strip()
        if not s:
            return None
        m = policy_head_re.match(s)
        if not m:
            return None
        pref = (m.group("ref") or "").strip()
        rest = (m.group("rest") or "").strip()
        title = rest.lstrip(": -\u2013\u2014").strip() or None
        return pref.upper(), title

    def looks_like_policy_code(text: str) -> bool:
        s = (text or "").strip()
        if not s or len(s) > 140:
            return False
        if re.match(r"^policy\\b", s, flags=re.IGNORECASE):
            return True
        if re.match(r"^[A-Za-z]{1,6}\\d+[A-Za-z]?\\b", s):
            return True
        return False

    # --- Policy sectioning (LLM instrument; avoids brittle regex-only extraction).
    # We still use deterministic heuristics only as a *candidate prefilter*.
    candidate_headings: list[dict[str, Any]] = []
    allowed_evidence_refs: set[str] = set()
    evidence_ref_by_row_id: dict[str, str] = {}
    row_index_by_evidence_ref: dict[str, int] = {}

    for idx, r in enumerate(rows):
        rid = str(r.get("id") or "")
        if not rid:
            continue
        frag = str(r.get("fragment_id") or "page-unknown")
        ev = f"chunk::{rid}::{frag}"
        evidence_ref_by_row_id[rid] = ev
        row_index_by_evidence_ref[ev] = idx
        allowed_evidence_refs.add(ev)

        txt = str(r.get("text") or "").strip()
        if not txt:
            continue
        ctype = (r.get("type") or "").lower()
        if ctype == "heading" or looks_like_policy_code(txt):
            candidate_headings.append(
                {
                    "evidence_ref": ev,
                    "page_number": r.get("page_number"),
                    "type": r.get("type"),
                    "section_path": r.get("section_path"),
                    "text": txt[:240],
                }
            )

    # Hard cap to keep prompt sizes bounded even on long documents.
    candidate_limit = 420
    if len(candidate_headings) > candidate_limit:
        # Prefer explicit headings; then fall back to the first N other candidates.
        headings = [c for c in candidate_headings if str(c.get("type") or "").lower() == "heading"]
        non_headings = [c for c in candidate_headings if str(c.get("type") or "").lower() != "heading"]
        candidate_headings = (headings + non_headings)[:candidate_limit]

    detected_headings: list[dict[str, Any]] = []
    if candidate_headings:
        policy_heading_json, policy_heading_tool_run_id, policy_heading_errors = _llm_structured_sync(
            prompt_id="ingest.policy_heading_detection",
            prompt_version=1,
            prompt_name="Policy heading detection",
            purpose="Identify policy headings in a planning document from candidate heading-like chunks (evidence refs must be chosen from the input list).",
            system_template=(
                "You are a UK planning policy parsing instrument.\n"
                "Task: from a list of candidate heading-like chunks (each with an EvidenceRef), identify which ones are POLICY HEADINGS.\n"
                "Return ONLY valid JSON.\n"
                "Output shape:\n"
                "{\n"
                "  \"policy_headings\": [\n"
                "    {\n"
                "      \"evidence_ref\": \"chunk::...::...\",\n"
                "      \"policy_code\": \"DM1\",\n"
                "      \"policy_title\": \"...\" | null,\n"
                "      \"confidence_hint\": \"low|medium|high|unknown\",\n"
                "      \"uncertainty_note\": string | null\n"
                "    }\n"
                "  ],\n"
                "  \"deliberate_omissions\": [ ... ]\n"
                "}\n"
                "Rules:\n"
                "- evidence_ref MUST be chosen only from the provided candidates; never invent citations.\n"
                "- If unsure, include the heading with confidence_hint=\"low\" and an uncertainty_note.\n"
                "- policy_code should be the short reference (e.g. DM1, SP2, H3, D1). If the heading is not a policy, omit it.\n"
            ),
            user_payload={
                "authority_id": authority_id,
                "plan_cycle_id": plan_cycle_id,
                "document_title": document_title,
                "candidates": candidate_headings,
                "max_policy_headings": 260,
            },
            time_budget_seconds=60.0,
            temperature=0.2,
            max_tokens=1200,
            output_schema_ref="schemas/PolicyHeadingDetectionResult.schema.json",
            ingest_batch_id=ingest_batch_id,
        )

        if policy_heading_tool_run_id is None and policy_heading_errors == ["llm_unconfigured"]:
            # Stable provenance envelope when the LLM instrument is unavailable.
            policy_heading_tool_run_id = str(uuid4())
            started = _utc_now()
            _db_execute(
                """
                INSERT INTO tool_runs (
                  id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
                )
                VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
                """,
                (
                    policy_heading_tool_run_id,
                    ingest_batch_id,
                    "policy_heading_detection_unavailable",
                    json.dumps({"authority_id": authority_id, "plan_cycle_id": plan_cycle_id, "document_id": document_id}, ensure_ascii=False),
                    json.dumps({"error": "llm_unconfigured"}, ensure_ascii=False),
                    "error",
                    started,
                    _utc_now(),
                    "low",
                    "Policy heading detection requires an LLM instrument; start the LLM service for this profile to enable it.",
                ),
            )

        raw = policy_heading_json.get("policy_headings") if isinstance(policy_heading_json, dict) else None
        if isinstance(raw, list):
            for item in raw[:300]:
                if not isinstance(item, dict):
                    continue
                ev = item.get("evidence_ref")
                code = item.get("policy_code")
                if not isinstance(ev, str) or ev not in allowed_evidence_refs:
                    continue
                if not isinstance(code, str) or not code.strip():
                    continue
                detected_headings.append(
                    {
                        "evidence_ref": ev,
                        "policy_ref": code.strip().upper(),
                        "policy_title": item.get("policy_title") if isinstance(item.get("policy_title"), str) else None,
                        "confidence_hint": item.get("confidence_hint") if isinstance(item.get("confidence_hint"), str) else None,
                        "uncertainty_note": item.get("uncertainty_note") if isinstance(item.get("uncertainty_note"), str) else None,
                    }
                )

    extracted: list[dict[str, Any]] = []
    used_llm_heading_detection = bool(detected_headings)

    if detected_headings:
        # Deterministic grouping by chunk order; non-deterministic heading selection is logged via tool_run_id.
        seen_ev: set[str] = set()
        ordered = []
        for h in detected_headings:
            ev = h["evidence_ref"]
            if ev in seen_ev:
                continue
            seen_ev.add(ev)
            ordered.append(h)
        ordered.sort(key=lambda h: row_index_by_evidence_ref.get(h["evidence_ref"], 10**9))

        start_indices = [row_index_by_evidence_ref[h["evidence_ref"]] for h in ordered if h["evidence_ref"] in row_index_by_evidence_ref]
        for i, h in enumerate(ordered):
            start = row_index_by_evidence_ref.get(h["evidence_ref"])
            if start is None:
                continue
            end = (start_indices[i + 1] - 1) if i + 1 < len(start_indices) else (len(rows) - 1)
            chunk_rows = rows[start : end + 1]
            extracted.append(
                {
                    "policy_ref": h["policy_ref"],
                    "policy_title": h.get("policy_title"),
                    "policy_heading_evidence_ref": h["evidence_ref"],
                    "confidence_hint": h.get("confidence_hint"),
                    "uncertainty_note": h.get("uncertainty_note"),
                    "policy_heading_detection_tool_run_id": policy_heading_tool_run_id,
                    "policy_heading_detection_errors": policy_heading_errors[:10],
                    "chunk_rows": chunk_rows,
                }
            )

    if not extracted and not require_llm_heading:
        # Fallback: deterministic heading detection (used only when explicitly allowed).
        current: dict[str, Any] | None = None
        for r in rows:
            ctype = (r.get("type") or "").lower()
            txt = str(r.get("text") or "").strip()
            if not txt:
                continue
            heading = parse_policy_heading(txt) if ctype == "heading" else None
            if heading:
                if current:
                    extracted.append(current)
                policy_ref, policy_title = heading
                current = {"policy_ref": policy_ref, "policy_title": policy_title, "chunk_rows": [r]}
                continue
            if current:
                current["chunk_rows"].append(r)
        if current:
            extracted.append(current)

    policy_ids: list[str] = []
    clause_ids: list[str] = []
    clause_texts_for_embedding: list[str] = []

    for p in extracted:
        chunk_rows = p.get("chunk_rows") if isinstance(p.get("chunk_rows"), list) else []
        if not chunk_rows:
            continue

        policy_ref = p.get("policy_ref")
        policy_title = p.get("policy_title")
        if not isinstance(policy_ref, str) or not policy_ref.strip():
            continue

        policy_confidence_hint = p.get("confidence_hint") if isinstance(p.get("confidence_hint"), str) else None
        if policy_confidence_hint not in {"low", "medium", "high", "unknown"}:
            policy_confidence_hint = None
        policy_uncertainty_note = p.get("uncertainty_note") if isinstance(p.get("uncertainty_note"), str) else None
        policy_heading_evidence_ref = (
            p.get("policy_heading_evidence_ref") if isinstance(p.get("policy_heading_evidence_ref"), str) else None
        )
        policy_heading_detection_tool_run_id = (
            p.get("policy_heading_detection_tool_run_id")
            if isinstance(p.get("policy_heading_detection_tool_run_id"), str)
            else None
        )
        policy_heading_detection_errors = (
            p.get("policy_heading_detection_errors")
            if isinstance(p.get("policy_heading_detection_errors"), list)
            else []
        )
        policy_heading_detection_errors = [e for e in policy_heading_detection_errors if isinstance(e, str)][:20]

        chunk_ids = [str(cr["id"]) for cr in chunk_rows if isinstance(cr, dict) and cr.get("id")]
        evidence_refs = [
            f"chunk::{cr['id']}::{cr.get('fragment_id') or 'page-unknown'}"
            for cr in chunk_rows
            if isinstance(cr, dict) and cr.get("id")
        ]
        policy_text = "\\n\\n".join(
            [str(cr.get("text") or "").strip() for cr in chunk_rows if isinstance(cr, dict) and cr.get("text")]
        ).strip()
        if not policy_text:
            continue

        policy_id = str(uuid4())

        _db_execute(
            """
            INSERT INTO policies (
              id, authority_id, ingest_batch_id, plan_cycle_id,
              policy_status, policy_weight_hint, effective_from, effective_to,
              applicability_jsonb, is_active, confidence_hint, uncertainty_note,
              text, overarching_policy_id, metadata
            )
            VALUES (
              %s, %s, %s::uuid, %s::uuid,
              %s, %s, %s, %s,
              '{}'::jsonb, true, %s, %s,
              %s, NULL, %s::jsonb
            )
            """,
            (
                policy_id,
                authority_id,
                ingest_batch_id,
                plan_cycle_id,
                plan_cycle_status,
                plan_cycle_weight_hint,
                effective_from,
                effective_to,
                policy_confidence_hint,
                policy_uncertainty_note,
                policy_text,
                json.dumps(
                    {
                        "document_id": document_id,
                        "document_title": document_title,
                        "policy_ref": f"Policy {policy_ref}",
                        "policy_code": policy_ref,
                        "policy_title": policy_title,
                        "policy_heading_evidence_ref": policy_heading_evidence_ref,
                        "policy_heading_detection_tool_run_id": policy_heading_detection_tool_run_id,
                        "policy_heading_detection_errors": policy_heading_detection_errors,
                        "extraction_method": (
                            "llm_policy_heading_detection_v1"
                            if policy_heading_detection_tool_run_id
                            else "policy_heading_candidate_v1"
                        ),
                        "chunk_ids": chunk_ids,
                        "evidence_refs": evidence_refs,
                    },
                    ensure_ascii=False,
                ),
            ),
        )

        # LLM parse per policy section: returns clause fragments + modality characterisation.
        source_chunks: list[dict[str, Any]] = []
        ev_to_section_path: dict[str, str | None] = {}
        for cr in chunk_rows:
            ev = f"chunk::{cr['id']}::{cr.get('fragment_id') or 'page-unknown'}"
            source_chunks.append(
                {
                    "evidence_ref": ev,
                    "type": cr.get("type"),
                    "section_path": cr.get("section_path"),
                    "text": cr.get("text"),
                }
            )
            ev_to_section_path[ev] = cr.get("section_path")

        clauses, policy_parse_tool_run_id, policy_parse_errors, policy_level_notes = _llm_parse_policy_clauses_for_section_sync(
            ingest_batch_id=ingest_batch_id,
            authority_id=authority_id,
            plan_cycle_id=plan_cycle_id,
            policy_ref=str(policy_ref),
            policy_title=policy_title if isinstance(policy_title, str) else None,
            source_chunks=source_chunks,
            time_budget_seconds=45.0,
        )

        require_llm = os.environ.get("TPA_POLICY_PARSE_REQUIRE_LLM", "true").strip().lower() in {"1", "true", "yes", "y"}
        if not clauses and require_llm:
            clauses = []

        if not clauses and not require_llm:
            clauses = [
                {
                    "clause_ref": None,
                    "text": policy_text,
                    "source_evidence_refs": evidence_refs[:10],
                    "speech_act": _normalize_policy_speech_act(
                        {
                            "normative_force": "unknown",
                            "strength_hint": "unknown",
                            "ambiguity_flags": ["insufficient_source_binding"],
                            "key_terms": [],
                            "officer_interpretation_space": "unknown",
                            "limitations_text": (
                                "Fallback clause created without an LLM parse; do not treat as a binding test. "
                                "Start the LLM service and re-ingest/re-parse for clause segmentation + modality."
                            ),
                        },
                        tool_run_id=policy_parse_tool_run_id,
                        method="fallback_no_llm_parse_v1",
                    ),
                }
            ]

        clause_count = 0
        for idx, cl in enumerate(clauses, start=1):
            clause_text = cl.get("text") if isinstance(cl.get("text"), str) else ""
            clause_text = clause_text.strip()
            if not clause_text:
                continue

            suffix = cl.get("clause_ref") if isinstance(cl.get("clause_ref"), str) else None
            base_ref = f"Policy {policy_ref}"
            clause_ref = base_ref if not suffix else (suffix.strip() if suffix.lower().startswith("policy") else f"{base_ref} {suffix.strip()}")

            clause_id = str(uuid4())
            src_refs = cl.get("source_evidence_refs") if isinstance(cl.get("source_evidence_refs"), list) else []
            src_refs = [r for r in src_refs if isinstance(r, str) and "::" in r][:30]
            section_path = ev_to_section_path.get(src_refs[0]) if src_refs else (chunk_rows[0].get("section_path") if chunk_rows else None)

            speech_act = _normalize_policy_speech_act(
                cl.get("speech_act"),
                tool_run_id=policy_parse_tool_run_id,
                method="llm_policy_clause_parse_v1",
            )

            _db_execute(
                """
                INSERT INTO policy_clauses (id, policy_id, clause_ref, text, metadata)
                VALUES (%s, %s::uuid, %s, %s, %s::jsonb)
                """,
                (
                    clause_id,
                    policy_id,
                    clause_ref,
                    clause_text,
                    json.dumps(
                        {
                            "section_path": section_path,
                            "document_id": document_id,
                            "document_title": document_title,
                            "chunk_ids": chunk_ids,
                            "evidence_refs": src_refs,
                            "speech_act": speech_act,
                            "policy_parse_tool_run_id": policy_parse_tool_run_id,
                            "policy_parse_errors": (policy_parse_errors or [])[:20],
                            "policy_level_notes": policy_level_notes,
                            "extraction_method": "llm_policy_clause_parse_v1",
                            "clause_index": idx,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            _ensure_evidence_ref_row(f"policy_clause::{clause_id}::text")
            clause_ids.append(clause_id)
            clause_texts_for_embedding.append(clause_text[:4000])
            clause_count += 1

        try:
            _db_execute(
                "UPDATE policies SET metadata = metadata || %s::jsonb WHERE id = %s::uuid",
                (
                    json.dumps(
                        {
                            "policy_parse_tool_run_id": policy_parse_tool_run_id,
                            "policy_parse_errors": (policy_parse_errors or [])[:20],
                            "policy_level_notes": policy_level_notes,
                            "clause_count": clause_count,
                        },
                        ensure_ascii=False,
                    ),
                    policy_id,
                ),
            )
        except Exception:  # noqa: BLE001
            pass

        policy_ids.append(policy_id)

    embeddings_inserted = 0
    embed_tool_run_id: str | None = None

    if embed_policy_clause_embeddings and clause_ids:
        embed_model_id = os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B")
        embed_started = _utc_now()
        embed_errors: list[str] = []

        # IMPORTANT: insert the ToolRun before inserting embeddings, otherwise FK checks can fail.
        tool_run_id_fk: str | None = str(uuid4())
        try:
            _db_execute(
                """
                INSERT INTO tool_runs (
                  id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
                  started_at, ended_at, confidence_hint, uncertainty_note
                )
                VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, %s, %s)
                """,
                (
                    tool_run_id_fk,
                    ingest_batch_id,
                    "embed_policy_clauses",
                    json.dumps({"model_id": embed_model_id, "clause_count": len(clause_ids)}, ensure_ascii=False),
                    json.dumps({}, ensure_ascii=False),
                    "running",
                    embed_started,
                    "medium",
                    "Generating policy clause embeddings...",
                ),
            )
        except Exception as exc:
            embed_errors.append(f"tool_run_insert_failed: {exc}")
            # Fallback: persist without ingest_batch_id if the FK is blocking (stale batch id / cross-run reuse).
            try:
                _db_execute(
                    """
                    INSERT INTO tool_runs (
                      id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
                      started_at, ended_at, confidence_hint, uncertainty_note
                    )
                    VALUES (%s, NULL, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, %s, %s)
                    """,
                    (
                        tool_run_id_fk,
                        "embed_policy_clauses",
                        json.dumps({"model_id": embed_model_id, "clause_count": len(clause_ids)}, ensure_ascii=False),
                        json.dumps({}, ensure_ascii=False),
                        "running",
                        embed_started,
                        "medium",
                        "Generating policy clause embeddings (ingest batch unknown).",
                    ),
                )
            except Exception as exc2:
                embed_errors.append(f"tool_run_insert_failed_fallback_null_ingest_batch: {exc2}")
                tool_run_id_fk = None

        if tool_run_id_fk and (not _db_fetch_one("SELECT 1 FROM tool_runs WHERE id = %s::uuid", (tool_run_id_fk,))):
            embed_errors.append("tool_run_not_persisted")
            tool_run_id_fk = None

        embeddings = _embed_texts_sync(texts=clause_texts_for_embedding, model_id=embed_model_id, time_budget_seconds=60.0)
        if embeddings and len(embeddings) == len(clause_ids):
            for clause_id, vec in zip(clause_ids, embeddings, strict=True):
                try:
                    _db_execute(
                        """
                        INSERT INTO policy_clause_embeddings (
                          id, policy_clause_id, embedding, embedding_model_id, created_at, tool_run_id
                        )
                        VALUES (%s, %s::uuid, %s::vector, %s, %s, %s::uuid)
                        ON CONFLICT (policy_clause_id, embedding_model_id) DO NOTHING
                        """,
                        (
                            str(uuid4()),
                            clause_id,
                            _vector_literal(vec),
                            embed_model_id,
                            _utc_now(),
                            tool_run_id_fk,
                        ),
                    )
                    embeddings_inserted += 1
                except Exception as exc:  # noqa: BLE001
                    embed_errors.append(str(exc))
        else:
            embed_errors.append("embeddings_unavailable_or_failed")

        embed_ended = _utc_now()
        status_final = (
            "success"
            if (embeddings_inserted > 0 and not embed_errors)
            else ("partial" if embeddings_inserted > 0 else "error")
        )
        if tool_run_id_fk:
            _db_execute(
                """
                UPDATE tool_runs
                SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                    confidence_hint = %s, uncertainty_note = %s
                WHERE id = %s::uuid
                """,
                (
                    status_final,
                    json.dumps({"inserted": embeddings_inserted, "errors": embed_errors[:20]}, ensure_ascii=False),
                    embed_ended,
                    "medium" if embeddings_inserted > 0 else "low",
                    (
                        "Embeddings support clause-aware retrieval; not a determination of policy weight or relevance."
                        if embeddings_inserted > 0
                        else "Policy clause embeddings were not generated; start the embeddings service (or enable the model supervisor)."
                    ),
                    tool_run_id_fk,
                ),
            )

        embed_tool_run_id = tool_run_id_fk

    _db_execute(
        """
        INSERT INTO tool_runs (
          id, ingest_batch_id, tool_name, inputs_logged, outputs_logged,
          status, started_at, ended_at, confidence_hint, uncertainty_note
        )
        VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
        """,
        (
            extraction_tool_run_id,
            ingest_batch_id,
            "extract_policy_clauses",
            json.dumps(
                {
                    "document_id": document_id,
                    "document_title": document_title,
                    "plan_cycle_id": plan_cycle_id,
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "policies_created": len(policy_ids),
                    "policy_clauses_created": len(clause_ids),
                    "evidence_ref_sample": [f"policy_clause::{cid}::text" for cid in clause_ids[:10]],
                    "embed_tool_run_id": embed_tool_run_id,
                    "embeddings_inserted": embeddings_inserted,
                    "embed_policy_clause_embeddings": bool(embed_policy_clause_embeddings),
                    "policy_heading_detection_tool_run_id": policy_heading_tool_run_id,
                    "policy_heading_detection_errors": policy_heading_errors[:10],
                    "policy_heading_detection_candidate_count": len(candidate_headings) if isinstance(candidate_headings, list) else None,
                    "policy_heading_detection_require_llm": bool(require_llm_heading),
                },
                ensure_ascii=False,
            ),
            "success",
            extraction_started,
            _utc_now(),
            "medium",
            "Policy clause extraction uses an LLM instrument; outputs are non-deterministic and preserve ambiguity. Treat as parsing aids, not binding requirements.",
        ),
    )

    return {
        "skipped": False,
        "policies_created": len(policy_ids),
        "policy_clauses_created": len(clause_ids),
        "embeddings_inserted": embeddings_inserted,
        "embed_tool_run_id": embed_tool_run_id,
        "tool_run_id": extraction_tool_run_id,
        "policy_ids": policy_ids[:20],
        "policy_clause_ids": clause_ids[:20],
    }


def _extract_pdf_pages_text(*, path: Path) -> tuple[list[str], str, list[dict[str, Any]]]:
    """
    Returns (page_texts, provider_name, chunks).

    Provider selection:
    - If `TPA_DOCPARSE_BASE_URL` is set, the API will call that DocParseProvider service first.
    - `TPA_DOCPARSE_PROVIDER=docling` will attempt Docling first and fall back to PyPDF.
    - default uses PyPDF.
    """
    base_url = os.environ.get("TPA_DOCPARSE_BASE_URL")
    if base_url:
        try:
            url = base_url.rstrip("/") + "/parse/pdf"
            with path.open("rb") as f:
                files = {"file": (path.name, f, "application/pdf")}
                with httpx.Client(timeout=120.0) as client:
                    resp = client.post(url, files=files)
                    resp.raise_for_status()
                    data = resp.json()
            page_texts = []
            chunks: list[dict[str, Any]] = []
            if isinstance(data, dict):
                if isinstance(data.get("page_texts"), list):
                    page_texts = [str(x) if isinstance(x, str) else "" for x in data["page_texts"]]
                pages_items = data.get("pages")
                if not page_texts and isinstance(pages_items, list):
                    for item in pages_items:
                        if isinstance(item, dict) and isinstance(item.get("text"), str):
                            page_texts.append(item["text"])
                raw_chunks = data.get("chunks")
                if isinstance(raw_chunks, list):
                    for ch in raw_chunks[:2000]:
                        if not isinstance(ch, dict):
                            continue
                        txt = ch.get("text")
                        if not isinstance(txt, str) or not txt.strip():
                            continue
                        chunks.append(
                            {
                                "text": txt,
                                "type": ch.get("type") if isinstance(ch.get("type"), str) else None,
                                "section_path": ch.get("section_path") if isinstance(ch.get("section_path"), str) else None,
                                "page_number": ch.get("page_number") if isinstance(ch.get("page_number"), int) else None,
                                "bbox": ch.get("bbox") if isinstance(ch.get("bbox"), (dict, list)) else None,
                            }
                        )
            if page_texts or chunks:
                provider = data.get("provider") if isinstance(data, dict) else None
                return page_texts, str(provider or "docparse_service"), chunks
        except Exception:  # noqa: BLE001
            pass

    prefer = os.environ.get("TPA_DOCPARSE_PROVIDER", "").strip().lower()
    if prefer == "docling":
        try:
            from docling.document_converter import DocumentConverter  # type: ignore[import-not-found]

            converter = DocumentConverter()
            result = converter.convert(str(path))
            doc = getattr(result, "document", result)
            pages = getattr(doc, "pages", None)
            if isinstance(pages, list) and pages:
                texts: list[str] = []
                for p in pages:
                    t = getattr(p, "text", None) or getattr(p, "text_content", None)
                    texts.append(t if isinstance(t, str) else "")
                return texts, "docling", []
        except Exception:  # noqa: BLE001
            pass

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    page_texts: list[str] = []
    for p in reader.pages:
        try:
            t = p.extract_text() or ""
        except Exception:  # noqa: BLE001
            t = ""
        page_texts.append(t)
    return page_texts, "pypdf", []


def _authority_packs_root() -> Path:
    return Path(os.environ.get("TPA_AUTHORITY_PACKS_ROOT", "/authority_packs")).resolve()


def _load_authority_pack_manifest(authority_id: str) -> dict[str, Any]:
    root = _authority_packs_root() / authority_id
    json_path = root / "manifest.json"
    yaml_path = root / "manifest.yaml"
    if json_path.exists():
        return _read_json(json_path)
    if yaml_path.exists():
        return _read_yaml(yaml_path)
    raise HTTPException(status_code=404, detail=f"Authority pack manifest not found for '{authority_id}'")


def _is_http_url(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
    except Exception:  # noqa: BLE001
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return cleaned or "document"


def _derive_filename_for_url(url: str, *, content_type: str | None = None) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name or "document"
    name = _sanitize_filename(name)
    stem = Path(name).stem or "document"
    suffix = Path(name).suffix
    if not suffix and content_type:
        suffix = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ""
    if not suffix:
        suffix = ".pdf"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{stem}-{digest}{suffix}"


def _web_automation_ingest_url(
    *,
    url: str,
    ingest_batch_id: str,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    base_url = os.environ.get("TPA_WEB_AUTOMATION_BASE_URL")
    if not base_url:
        return {"ok": False, "error": "web_automation_unconfigured"}

    tool_run_id = str(uuid4())
    started = _utc_now()
    tool_run_inserted = False
    try:
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
              started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, %s, %s)
            """,
            (
                tool_run_id,
                ingest_batch_id,
                "web_ingest",
                json.dumps({"url": url, "base_url": base_url}, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                "running",
                started,
                "low",
                "Web capture requested; awaiting response.",
            ),
        )
        tool_run_inserted = True
    except Exception:  # noqa: BLE001
        tool_run_inserted = False

    payload = {
        "url": url,
        "timeout_ms": int(timeout_seconds * 1000),
        "max_bytes": int(os.environ.get("TPA_WEB_MAX_FETCH_BYTES", "12000000")),
        "screenshot": False,
    }

    try:
        with httpx.Client(timeout=timeout_seconds + 5.0) as client:
            resp = client.post(base_url.rstrip("/") + "/ingest", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        if tool_run_inserted:
            _db_execute(
                """
                UPDATE tool_runs
                SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                    confidence_hint = %s, uncertainty_note = %s
                WHERE id = %s::uuid
                """,
                (
                    "error",
                    json.dumps({"error": str(exc)}, ensure_ascii=False),
                    _utc_now(),
                    "low",
                    "Web capture failed; check web automation service connectivity.",
                    tool_run_id,
                ),
            )
        return {"ok": False, "error": f"web_ingest_failed: {exc}", "tool_run_id": tool_run_id}

    content_type = data.get("content_type")
    content_type_norm = str(content_type or "").lower()
    if "pdf" not in content_type_norm:
        if tool_run_inserted:
            _db_execute(
                """
                UPDATE tool_runs
                SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                    confidence_hint = %s, uncertainty_note = %s
                WHERE id = %s::uuid
                """,
                (
                    "partial",
                    json.dumps(
                        {
                            "content_type": content_type,
                            "final_url": data.get("final_url"),
                            "http_status": data.get("http_status"),
                        },
                        ensure_ascii=False,
                    ),
                    _utc_now(),
                    "low",
                    "Web capture succeeded but did not return a PDF payload.",
                    tool_run_id,
                ),
            )
        return {
            "ok": False,
            "error": f"unsupported_content_type:{content_type}",
            "tool_run_id": tool_run_id,
        }

    payload_b64 = data.get("content_base64")
    if not isinstance(payload_b64, str) or not payload_b64:
        if tool_run_inserted:
            _db_execute(
                """
                UPDATE tool_runs
                SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                    confidence_hint = %s, uncertainty_note = %s
                WHERE id = %s::uuid
                """,
                (
                    "error",
                    json.dumps({"error": "missing_content_base64"}, ensure_ascii=False),
                    _utc_now(),
                    "low",
                    "Web capture returned an empty payload.",
                    tool_run_id,
                ),
            )
        return {"ok": False, "error": "missing_content_base64", "tool_run_id": tool_run_id}

    try:
        data_bytes = base64.b64decode(payload_b64)
    except Exception as exc:  # noqa: BLE001
        if tool_run_inserted:
            _db_execute(
                """
                UPDATE tool_runs
                SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                    confidence_hint = %s, uncertainty_note = %s
                WHERE id = %s::uuid
                """,
                (
                    "error",
                    json.dumps({"error": str(exc)}, ensure_ascii=False),
                    _utc_now(),
                    "low",
                    "Web capture payload could not be decoded.",
                    tool_run_id,
                ),
            )
        return {"ok": False, "error": f"decode_failed:{exc}", "tool_run_id": tool_run_id}

    if content_type_norm == "pdf":
        content_type = "application/pdf"

    outputs = {
        "content_type": content_type,
        "content_bytes": len(data_bytes),
        "final_url": data.get("final_url"),
        "requested_url": data.get("requested_url"),
        "http_status": data.get("http_status"),
        "limitations_text": data.get("limitations_text"),
        "filename": data.get("filename"),
    }
    if tool_run_inserted:
        _db_execute(
            """
            UPDATE tool_runs
            SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                confidence_hint = %s, uncertainty_note = %s
            WHERE id = %s::uuid
            """,
            (
                "success",
                json.dumps(outputs, ensure_ascii=False),
                _utc_now(),
                "medium",
                "Web capture delivered a PDF payload; treat as evidence artefact.",
                tool_run_id,
            ),
        )

    return {
        "ok": True,
        "bytes": data_bytes,
        "content_type": content_type,
        "final_url": data.get("final_url") or url,
        "requested_url": data.get("requested_url") or url,
        "filename": data.get("filename"),
        "limitations_text": data.get("limitations_text"),
        "tool_run_id": tool_run_id,
    }


def _normalize_authority_pack_documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw = manifest.get("documents", [])
    if raw is None:
        return []
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        out: list[dict[str, Any]] = []
        for item in raw:
            if _is_http_url(item):
                title = Path(urlparse(item).path).stem or "document"
                out.append({"file_path": None, "source_url": item, "title": title, "source": "web_automation"})
            else:
                out.append({"file_path": item, "title": Path(item).stem, "source": "authority_pack"})
        return out
    if isinstance(raw, list) and all(isinstance(x, dict) for x in raw):
        out: list[dict[str, Any]] = []
        for d in raw:
            fp = d.get("file_path") or d.get("path") or d.get("file")
            source_url = d.get("url") or d.get("source_url") or d.get("href")
            if not fp and not source_url:
                continue
            title_hint = d.get("title")
            if not title_hint:
                if source_url:
                    title_hint = Path(urlparse(str(source_url)).path).stem or "document"
                if not title_hint and fp:
                    title_hint = Path(str(fp)).stem
            out.append(
                {
                    "file_path": fp,
                    "source_url": source_url,
                    "title": title_hint,
                    "document_type": d.get("type") or d.get("document_type"),
                    "source": d.get("source") or ("web_automation" if source_url else "authority_pack"),
                    "published_date": d.get("published_date") or d.get("date"),
                }
            )
        return out
    return []


class PlanCycleInline(BaseModel):
    plan_name: str
    status: str
    weight_hint: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthorityPackIngestRequest(BaseModel):
    source_system: str = Field(default="authority_pack")
    plan_cycle_id: str | None = None
    plan_cycle: PlanCycleInline | None = None
    notes: str | None = None


def _prepare_authority_pack_ingest(
    *,
    authority_id: str,
    body: AuthorityPackIngestRequest,
    manifest: dict[str, Any],
    document_count: int,
) -> tuple[dict[str, Any], str, str, str, datetime]:
    """
    Creates (or resolves) a plan cycle + creates an ingest_batch envelope.

    Returns: (plan_cycle_row, plan_cycle_id, ingest_batch_id, tool_run_id, started_at)
    """
    try:
        plan_cycle_row: dict[str, Any] | None = None
        plan_cycle_id = body.plan_cycle_id
        if plan_cycle_id:
            plan_cycle_id = _validate_uuid_or_400(plan_cycle_id, field_name="plan_cycle_id")
            plan_cycle_row = _db_fetch_one(
                """
                SELECT id, authority_id, plan_name, status, weight_hint, effective_from, effective_to
                FROM plan_cycles
                WHERE id = %s::uuid
                """,
                (plan_cycle_id,),
            )
            if not plan_cycle_row:
                raise HTTPException(status_code=404, detail="plan_cycle_id not found")
            if plan_cycle_row["authority_id"] != authority_id:
                raise HTTPException(status_code=400, detail="plan_cycle_id does not belong to this authority_id")
        else:
            if body.plan_cycle is None:
                raise HTTPException(
                    status_code=400,
                    detail="Provide either plan_cycle_id or plan_cycle {plan_name,status,...} to make authority versioning explicit.",
                )
            now = _utc_now()
            plan_cycle_row = _db_execute_returning(
                """
                INSERT INTO plan_cycles (
                  id, authority_id, plan_name, status, weight_hint, effective_from, effective_to,
                  metadata_jsonb, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING id, authority_id, plan_name, status, weight_hint, effective_from, effective_to
                """,
                (
                    str(uuid4()),
                    authority_id,
                    body.plan_cycle.plan_name,
                    body.plan_cycle.status,
                    body.plan_cycle.weight_hint,
                    body.plan_cycle.effective_from,
                    body.plan_cycle.effective_to,
                    json.dumps(body.plan_cycle.metadata, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            plan_cycle_id = str(plan_cycle_row["id"])
            _audit_event(
                event_type="plan_cycle_created",
                actor_type="system",
                payload={"plan_cycle_id": plan_cycle_id, "authority_id": authority_id, "status": plan_cycle_row["status"]},
            )

        if not isinstance(plan_cycle_row, dict):
            raise HTTPException(status_code=500, detail="Failed to resolve plan cycle")

        ingest_batch_id = str(uuid4())
        tool_run_id = str(uuid4())
        started_at = _utc_now()

        _db_execute(
            """
            INSERT INTO ingest_batches (
              id, source_system, authority_id, plan_cycle_id,
              started_at, completed_at, status, notes,
              inputs_jsonb, outputs_jsonb
            )
            VALUES (%s, %s, %s, %s::uuid, %s, NULL, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                ingest_batch_id,
                body.source_system,
                authority_id,
                plan_cycle_id,
                started_at,
                "running",
                body.notes,
                json.dumps(
                    {
                        "authority_pack_id": manifest.get("id"),
                        "authority_pack_name": manifest.get("name"),
                        "document_count": int(document_count),
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"counts": {}, "errors": [], "progress": {"phase": "starting"}}, ensure_ascii=False),
            ),
        )

        return plan_cycle_row, str(plan_cycle_id), ingest_batch_id, tool_run_id, started_at
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "relation" in msg and any(t in msg for t in ["plan_cycles", "ingest_batches", "tool_runs", "documents", "chunks"]):
            raise HTTPException(
                status_code=500,
                detail=(
                    "Database schema appears out of date (missing expected tables). "
                    "If you pulled new repo changes after the first boot, reset the Postgres volume so init SQL runs: "
                    "`docker compose -f docker/compose.oss.yml down` then `docker volume rm tpa-oss_tpa_db_data` "
                    "then `docker compose -f docker/compose.oss.yml up -d --build`."
                ),
            ) from exc
        raise HTTPException(status_code=500, detail=f"Ingest setup failed: {msg}") from exc


def _update_ingest_batch_progress(
    *,
    ingest_batch_id: str,
    status: str,
    counts: dict[str, int],
    errors: list[str],
    document_ids: list[str],
    plan_cycle_id: str,
    progress: dict[str, Any],
) -> None:
    payload = {
        "counts": counts,
        "errors": errors[:50],
        "document_ids": document_ids[:200],
        "plan_cycle_id": plan_cycle_id,
        "progress": progress,
    }
    try:
        _db_execute(
            "UPDATE ingest_batches SET status = %s, outputs_jsonb = %s::jsonb WHERE id = %s::uuid",
            (status, json.dumps(payload, ensure_ascii=False), ingest_batch_id),
        )
    except Exception:  # noqa: BLE001
        pass


def _run_authority_pack_ingest(
    *,
    authority_id: str,
    pack_dir: Path,
    manifest: dict[str, Any],
    documents: list[dict[str, Any]],
    plan_cycle_row: dict[str, Any],
    plan_cycle_id: str,
    ingest_batch_id: str,
    tool_run_id: str,
    started_at: datetime,
) -> dict[str, Any]:
    errors: list[str] = []
    counts: dict[str, int] = {
        "documents_created": 0,
        "documents_seen": 0,
        "documents_skipped": 0,
        "pages": 0,
        "chunks": 0,
        "chunk_embeddings_inserted": 0,
        "policies_created": 0,
        "policy_clauses_created": 0,
        "policy_clause_embeddings_inserted": 0,
    }
    document_ids: list[str] = []
    status = "failed"
    minio_client = _minio_client_or_none()
    bucket = os.environ.get("TPA_S3_BUCKET")
    phased_default = "true" if os.environ.get("TPA_MODEL_SUPERVISOR_URL") else "false"
    phased = os.environ.get("TPA_INGEST_PHASED", phased_default).strip().lower() in {"1", "true", "yes", "y"}
    docs_for_postprocessing: list[dict[str, Any]] = []
    temp_paths: list[Path] = []

    _update_ingest_batch_progress(
        ingest_batch_id=ingest_batch_id,
        status="running",
        counts=counts,
        errors=errors,
        document_ids=document_ids,
        plan_cycle_id=plan_cycle_id,
        progress={"phase": "chunking", "current_document": None, "phased": phased},
    )

    try:
        if minio_client and bucket:
            try:
                if not minio_client.bucket_exists(bucket):
                    minio_client.make_bucket(bucket)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"MinIO bucket check failed: {exc}")
                minio_client = None

        for doc in documents:
            rel_path = doc.get("file_path")
            source_url = doc.get("source_url") or doc.get("url")
            if not source_url and _is_http_url(rel_path):
                source_url = str(rel_path)
                rel_path = None

            source_label = source_url or str(rel_path or "")
            if not source_label:
                continue

            counts["documents_seen"] += 1
            src_path: Path | None = None
            source_final_url = source_url
            content_type: str | None = None

            if source_url:
                try:
                    web_timeout = float(os.environ.get("TPA_WEB_AUTOMATION_TIMEOUT_SECONDS", "60"))
                except Exception:  # noqa: BLE001
                    web_timeout = 60.0
                ingest_result = _web_automation_ingest_url(
                    url=source_url,
                    ingest_batch_id=ingest_batch_id,
                    timeout_seconds=web_timeout,
                )
                if not ingest_result.get("ok"):
                    err = ingest_result.get("error") or "web_ingest_failed"
                    errors.append(f"Web ingest failed for {source_url}: {err}")
                    _update_ingest_batch_progress(
                        ingest_batch_id=ingest_batch_id,
                        status="running",
                        counts=counts,
                        errors=errors,
                        document_ids=document_ids,
                        plan_cycle_id=plan_cycle_id,
                        progress={"phase": "running", "current_document": source_label, "note": "web_ingest_failed"},
                    )
                    continue

                raw_content_type = str(ingest_result.get("content_type") or "").lower()
                if "pdf" not in raw_content_type:
                    errors.append(
                        f"Web ingest returned unsupported content for {source_url}: {raw_content_type or 'unknown'}"
                    )
                    _update_ingest_batch_progress(
                        ingest_batch_id=ingest_batch_id,
                        status="running",
                        counts=counts,
                        errors=errors,
                        document_ids=document_ids,
                        plan_cycle_id=plan_cycle_id,
                        progress={"phase": "running", "current_document": source_label, "note": "web_ingest_unsupported"},
                    )
                    continue

                data_bytes = ingest_result.get("bytes")
                if not isinstance(data_bytes, (bytes, bytearray)) or not data_bytes:
                    errors.append(f"Web ingest returned empty payload for {source_url}")
                    _update_ingest_batch_progress(
                        ingest_batch_id=ingest_batch_id,
                        status="running",
                        counts=counts,
                        errors=errors,
                        document_ids=document_ids,
                        plan_cycle_id=plan_cycle_id,
                        progress={"phase": "running", "current_document": source_label, "note": "web_ingest_empty"},
                    )
                    continue

                source_final_url = ingest_result.get("final_url") or source_url
                content_type = "application/pdf" if raw_content_type == "pdf" else ingest_result.get("content_type")
                content_type = content_type or "application/pdf"
                filename = ingest_result.get("filename") or _derive_filename_for_url(
                    source_final_url, content_type=content_type
                )
                temp_dir = Path(tempfile.mkdtemp(prefix="tpa-web-"))
                src_path = temp_dir / filename
                src_path.write_bytes(data_bytes)
            else:
                rel_path_str = str(rel_path or "")
                src_path = (pack_dir / rel_path_str).resolve()
                if not src_path.exists():
                    errors.append(f"Missing file: {src_path}")
                    _update_ingest_batch_progress(
                        ingest_batch_id=ingest_batch_id,
                        status="running",
                        counts=counts,
                        errors=errors,
                        document_ids=document_ids,
                        plan_cycle_id=plan_cycle_id,
                        progress={"phase": "running", "current_document": rel_path_str, "note": "missing_file"},
                    )
                    continue
                content_type = mimetypes.guess_type(src_path.name)[0] or "application/octet-stream"

            _update_ingest_batch_progress(
                ingest_batch_id=ingest_batch_id,
                status="running",
                counts=counts,
                errors=errors,
                document_ids=document_ids,
                plan_cycle_id=plan_cycle_id,
                progress={"phase": "chunking", "current_document": source_label, "phased": phased},
            )

            if not src_path:
                errors.append(f"Source path unavailable for {source_label}")
                continue

            object_name = (
                f"raw/web/{authority_id}/{src_path.name}"
                if source_url
                else f"raw/authority_packs/{authority_id}/{src_path.name}"
            )

            blob_path: str
            if minio_client and bucket:
                try:
                    try:
                        minio_client.stat_object(bucket, object_name)
                    except Exception:  # noqa: BLE001
                        minio_client.fput_object(bucket, object_name, str(src_path), content_type=content_type)
                    blob_path = object_name
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"MinIO upload failed for {src_path.name}: {exc}")
                    blob_path = str(src_path)
            else:
                blob_path = str(src_path)

            if source_url and src_path and blob_path != str(src_path):
                temp_paths.append(src_path)

            existing_doc = _db_fetch_one(
                """
                SELECT id
                FROM documents
                WHERE authority_id = %s
                  AND plan_cycle_id = %s::uuid
                  AND blob_path = %s
                """,
                (authority_id, plan_cycle_id, blob_path),
            )
            if existing_doc:
                document_id = str(existing_doc["id"])
            else:
                doc_title = doc.get("title") or src_path.stem
                metadata = {
                    "title": doc_title,
                    "document_type": doc.get("document_type"),
                    "source": doc.get("source") or ("web_automation" if source_url else "authority_pack"),
                    "content_type": content_type,
                }
                if source_url:
                    metadata["source_url"] = source_final_url or source_url
                    if source_final_url and source_final_url != source_url:
                        metadata["source_url_original"] = source_url
                document_id = str(uuid4())
                _db_execute(
                    """
                    INSERT INTO documents (
                      id, authority_id, ingest_batch_id, plan_cycle_id,
                      document_status, weight_hint, effective_from, effective_to,
                      metadata, blob_path
                    )
                    VALUES (%s, %s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    (
                        document_id,
                        authority_id,
                        ingest_batch_id,
                        plan_cycle_id,
                        plan_cycle_row.get("status"),
                        plan_cycle_row.get("weight_hint"),
                        plan_cycle_row.get("effective_from"),
                        plan_cycle_row.get("effective_to"),
                        json.dumps(metadata, ensure_ascii=False),
                        blob_path,
                    ),
                )
                counts["documents_created"] += 1

            document_ids.append(document_id)
            docs_for_postprocessing.append(
                {
                    "document_id": document_id,
                    "document_title": doc.get("title") or src_path.stem,
                    "source_rel_path": source_final_url or source_url or str(rel_path or ""),
                    "source_name": src_path.name,
                }
            )

            already_chunked = _db_fetch_one("SELECT 1 FROM chunks WHERE document_id = %s LIMIT 1", (document_id,))
            if already_chunked:
                counts["documents_skipped"] += 1
                if phased:
                    continue
                # Backfill missing embeddings for already-chunked documents (common after enabling embeddings later).
                embed_model_id = os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B")
                missing = _db_fetch_all(
                    """
                    SELECT c.id AS chunk_id, LEFT(c.text, 4000) AS text
                    FROM chunks c
                    LEFT JOIN chunk_embeddings ce
                      ON ce.chunk_id = c.id AND ce.embedding_model_id = %s
                    WHERE c.document_id = %s::uuid
                      AND ce.id IS NULL
                    """,
                    (embed_model_id, document_id),
                )
                if missing:
                    chunks_to_embed = [(str(r["chunk_id"]), str(r.get("text") or "")) for r in missing if r.get("chunk_id")]
                    chunks_to_embed = [(cid, t) for cid, t in chunks_to_embed if t.strip()]
                    if chunks_to_embed:
                        embed_tool_run_id = str(uuid4())
                        embed_started = _utc_now()
                        embed_errors: list[str] = []
                        inserted = 0
                        tool_run_id_fk: str | None = None

                        # Insert tool_run first to satisfy FK
                        try:
                            _db_execute(
                                """
                                INSERT INTO tool_runs (
                                  id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
                                  started_at, ended_at, confidence_hint, uncertainty_note
                                )
                                VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, null, %s, %s)
                                """,
                                (
                                    embed_tool_run_id,
                                    ingest_batch_id,
                                    "embed_chunks",
                                    json.dumps(
                                        {
                                            "chunk_count": len(chunks_to_embed),
                                            "model_id": embed_model_id,
                                            "mode": "backfill",
                                            "document_id": document_id,
                                            "document_title": doc.get("title") or src_path.stem,
                                            "embeddings_base_url": os.environ.get("TPA_EMBEDDINGS_BASE_URL"),
                                            "model_supervisor_url": os.environ.get("TPA_MODEL_SUPERVISOR_URL"),
                                        },
                                        ensure_ascii=False,
                                    ),
                                    json.dumps({}, ensure_ascii=False),
                                    "running",
                                    embed_started,
                                    "medium",
                                    "Generating embeddings...",
                                ),
                            )
                            tool_run_id_fk = embed_tool_run_id
                        except Exception as exc:
                            print(f"CRITICAL: Failed to insert tool_run {embed_tool_run_id}: {exc}", flush=True)
                            embed_errors.append(f"tool_run_insert_failed: {exc}")

                            # Fallback: persist without ingest_batch_id if the FK is blocking.
                            try:
                                _db_execute(
                                    """
                                    INSERT INTO tool_runs (
                                      id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
                                      started_at, ended_at, confidence_hint, uncertainty_note
                                    )
                                    VALUES (%s, NULL, %s, %s::jsonb, %s::jsonb, %s, %s, null, %s, %s)
                                    """,
                                    (
                                        embed_tool_run_id,
                                        "embed_chunks",
                                        json.dumps(
                                            {
                                                "chunk_count": len(chunks_to_embed),
                                                "model_id": embed_model_id,
                                                "mode": "backfill",
                                                "document_id": document_id,
                                                "document_title": doc.get("title") or src_path.stem,
                                                "embeddings_base_url": os.environ.get("TPA_EMBEDDINGS_BASE_URL"),
                                                "model_supervisor_url": os.environ.get("TPA_MODEL_SUPERVISOR_URL"),
                                            },
                                            ensure_ascii=False,
                                        ),
                                        json.dumps({}, ensure_ascii=False),
                                        "running",
                                        embed_started,
                                        "medium",
                                        "Generating embeddings (ingest batch unknown).",
                                    ),
                                )
                                tool_run_id_fk = embed_tool_run_id
                            except Exception as exc2:
                                embed_errors.append(f"tool_run_insert_failed_fallback_null_ingest_batch: {exc2}")
                                tool_run_id_fk = None

                        # Verify tool_run exists
                        if tool_run_id_fk and (
                            not _db_fetch_one("SELECT 1 FROM tool_runs WHERE id = %s::uuid", (embed_tool_run_id,))
                        ):
                            print(f"CRITICAL: tool_run {embed_tool_run_id} not found after insert!", flush=True)
                            embed_errors.append("tool_run_not_persisted")
                            tool_run_id_fk = None

                        try:
                            batch_size = int(os.environ.get("TPA_INGEST_EMBED_BATCH_SIZE", "96"))
                        except Exception:  # noqa: BLE001
                            batch_size = 96
                        batch_size = max(8, min(batch_size, 256))

                        for i in range(0, len(chunks_to_embed), batch_size):
                            batch = chunks_to_embed[i : i + batch_size]
                            embeddings = _embed_texts_sync(texts=[t for _, t in batch], model_id=embed_model_id)

                            if embeddings and len(embeddings) == len(batch):
                                for (chunk_id, _), vec in zip(batch, embeddings, strict=True):
                                    try:
                                        _db_execute(
                                            """
                                            INSERT INTO chunk_embeddings (
                                              id, chunk_id, embedding, embedding_model_id, created_at, tool_run_id
                                            )
                                            VALUES (%s, %s, %s::vector, %s, %s, %s::uuid)
                                            ON CONFLICT (chunk_id, embedding_model_id) DO NOTHING
                                            """,
                                            (
                                                str(uuid4()),
                                                chunk_id,
                                                _vector_literal(vec),
                                                embed_model_id,
                                                _utc_now(),
                                                tool_run_id_fk,
                                            ),
                                        )
                                        inserted += 1
                                    except Exception as exc:  # noqa: BLE001
                                        embed_errors.append(str(exc))
                            else:
                                embed_errors.append(f"embeddings_unavailable_or_failed_batch_{i//batch_size}")

                        embed_ended = _utc_now()
                        status_final = (
                            "success"
                            if (inserted > 0 and not embed_errors)
                            else ("partial" if inserted > 0 else "error")
                        )

                        if tool_run_id_fk:
                            _db_execute(
                                """
                                UPDATE tool_runs
                                SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                                    confidence_hint = %s, uncertainty_note = %s
                                WHERE id = %s
                                """,
                                (
                                    status_final,
                                    json.dumps(
                                        {
                                            "inserted": inserted,
                                            "embedding_dim": len(embeddings[0])
                                            if (inserted > 0 and "embeddings" in locals() and embeddings)
                                            else None,
                                            "errors": embed_errors[:20],
                                        },
                                        ensure_ascii=False,
                                    ),
                                    embed_ended,
                                    "medium" if inserted > 0 else "low",
                                    (
                                        "Embeddings generated for retrieval; model-dependent and not a determination of relevance."
                                        if inserted > 0
                                        else "Chunk embeddings were not generated; start the embeddings service (or enable the model supervisor)."
                                    ),
                                    embed_tool_run_id,
                                ),
                            )

                        if inserted == 0:
                            errors.append(
                                f"Chunk embeddings were not generated for existing document {src_path.name} (embeddings service unavailable or failed)."
                            )
                        counts["chunk_embeddings_inserted"] += inserted

                try:
                    doc_title = str(doc.get("title") or src_path.stem)
                    extracted = _extract_policies_from_document_chunks(
                        authority_id=authority_id,
                        plan_cycle_id=plan_cycle_id,
                        ingest_batch_id=ingest_batch_id,
                        document_id=document_id,
                        document_title=doc_title,
                        plan_cycle_status=plan_cycle_row.get("status"),
                        plan_cycle_weight_hint=plan_cycle_row.get("weight_hint"),
                        effective_from=plan_cycle_row.get("effective_from"),
                        effective_to=plan_cycle_row.get("effective_to"),
                    )
                    counts["policies_created"] += int(extracted.get("policies_created") or 0)
                    counts["policy_clauses_created"] += int(extracted.get("policy_clauses_created") or 0)
                    counts["policy_clause_embeddings_inserted"] += int(extracted.get("embeddings_inserted") or 0)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"Policy clause extraction failed for {src_path.name}: {exc}")
                continue

            docparse_tool_run_id = str(uuid4())
            docparse_started = _utc_now()
            try:
                page_texts, docparse_provider, parsed_chunks = _extract_pdf_pages_text(path=src_path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"PDF parse failed for {src_path.name}: {exc}")
                _db_execute(
                    """
                    INSERT INTO tool_runs (
                      id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
                      started_at, ended_at, confidence_hint, uncertainty_note
                    )
                    VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
                    """,
                    (
                        docparse_tool_run_id,
                        ingest_batch_id,
                        "doc_parse_pdf",
                        json.dumps({"path": str(src_path), "provider_requested": os.environ.get("TPA_DOCPARSE_PROVIDER")}),
                        json.dumps({"error": str(exc)}, ensure_ascii=False),
                        "error",
                        docparse_started,
                        _utc_now(),
                        "low",
                        "Document parsing failed; no chunks were produced.",
                    ),
                )
                continue

            docparse_ended = _utc_now()
            fallback_mode = os.environ.get("TPA_DOCPARSE_PROVIDER", "").strip().lower() == "docling" and docparse_provider != "docling"
            _db_execute(
                """
                INSERT INTO tool_runs (
                  id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
                  started_at, ended_at, confidence_hint, uncertainty_note
                )
                VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
                """,
                (
                    docparse_tool_run_id,
                    ingest_batch_id,
                    "doc_parse_pdf",
                    json.dumps(
                        {
                            "path": str(src_path),
                            "provider_requested": os.environ.get("TPA_DOCPARSE_PROVIDER") or "pypdf",
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "provider_used": docparse_provider,
                            "page_count": len(page_texts),
                            "chunk_count": len(parsed_chunks) if isinstance(parsed_chunks, list) else 0,
                            "fallback_mode": fallback_mode,
                        },
                        ensure_ascii=False,
                    ),
                    "partial" if fallback_mode else "success",
                    docparse_started,
                    docparse_ended,
                    "medium",
                    "Text extraction is an evidence instrument; layout/semantics may be imperfect (see limitations).",
                ),
            )

            chunks_to_embed: list[tuple[str, str]] = []

            # Always store per-page text as a canonical baseline (even if structured chunks exist).
            for idx, page_text in enumerate(page_texts, start=1):
                page_text = (page_text or "").strip()
                if not page_text:
                    continue
                page_id = str(uuid4())
                _db_execute(
                    """
                    INSERT INTO pages (id, document_id, page_number, metadata)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (document_id, page_number) DO NOTHING
                    """,
                    (page_id, document_id, idx, "{}"),
                )
                counts["pages"] += 1

            if parsed_chunks:
                for c_idx, ch in enumerate(parsed_chunks, start=1):
                    if not isinstance(ch, dict):
                        continue
                    chunk_text = str(ch.get("text") or "").strip()
                    if not chunk_text:
                        continue
                    chunk_id = str(uuid4())
                    page_number = ch.get("page_number") if isinstance(ch.get("page_number"), int) else None
                    fragment = f"p{page_number}-c{c_idx:03d}" if page_number else f"c{c_idx:04d}"
                    bbox = ch.get("bbox") if isinstance(ch.get("bbox"), (dict, list)) else None
                    _db_execute(
                        """
                        INSERT INTO chunks (id, document_id, page_number, text, bbox, type, section_path, metadata)
                        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                        """,
                        (
                            chunk_id,
                            document_id,
                            page_number,
                            chunk_text,
                            json.dumps(bbox, ensure_ascii=False) if bbox is not None else None,
                            ch.get("type") if isinstance(ch.get("type"), str) else None,
                            ch.get("section_path") if isinstance(ch.get("section_path"), str) else None,
                            json.dumps({"authority_id": authority_id, "evidence_ref_fragment": fragment}, ensure_ascii=False),
                        ),
                    )
                    counts["chunks"] += 1
                    evidence_ref_id = str(uuid4())
                    _db_execute(
                        "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id) VALUES (%s, %s, %s, %s)",
                        (evidence_ref_id, "chunk", chunk_id, fragment),
                    )
                    chunks_to_embed.append((chunk_id, chunk_text[:4000]))
            else:
                section_stack: list[str] = []
                for idx, page_text in enumerate(page_texts, start=1):
                    page_text = (page_text or "").strip()
                    if not page_text:
                        continue
                    lines = page_text.splitlines()
                    page_chunks, section_stack = _semantic_chunk_lines(lines=lines, section_stack=section_stack)
                    for c_idx, ch in enumerate(page_chunks, start=1):
                        chunk_text = str(ch.get("text") or "").strip()
                        if not chunk_text:
                            continue
                        chunk_id = str(uuid4())
                        fragment = f"p{idx}-c{c_idx:03d}"
                        _db_execute(
                            """
                            INSERT INTO chunks (id, document_id, page_number, text, bbox, type, section_path, metadata)
                            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                            """,
                            (
                                chunk_id,
                                document_id,
                                idx,
                                chunk_text,
                                None,
                                ch.get("type"),
                                ch.get("section_path"),
                                json.dumps({"authority_id": authority_id, "evidence_ref_fragment": fragment}, ensure_ascii=False),
                            ),
                        )
                        counts["chunks"] += 1
                        evidence_ref_id = str(uuid4())
                        _db_execute(
                            "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id) VALUES (%s, %s, %s, %s)",
                            (evidence_ref_id, "chunk", chunk_id, fragment),
                        )
                        chunks_to_embed.append((chunk_id, chunk_text[:4000]))

            if (not phased) and chunks_to_embed:
                embed_model_id = os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B")
                embed_tool_run_id = str(uuid4())
                embed_started = _utc_now()
                embed_errors: list[str] = []
                inserted = 0
                tool_run_id_fk: str | None = None

                # Insert tool_run first to satisfy FK
                try:
                    _db_execute(
                        """
                        INSERT INTO tool_runs (
                          id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
                          started_at, ended_at, confidence_hint, uncertainty_note
                        )
                        VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, null, %s, %s)
                        """,
                        (
                            embed_tool_run_id,
                            ingest_batch_id,
                            "embed_chunks",
                            json.dumps(
                                {
                                    "chunk_count": len(chunks_to_embed),
                                    "model_id": embed_model_id,
                                    "embeddings_base_url": os.environ.get("TPA_EMBEDDINGS_BASE_URL"),
                                    "model_supervisor_url": os.environ.get("TPA_MODEL_SUPERVISOR_URL"),
                                },
                                ensure_ascii=False,
                            ),
                            json.dumps({}, ensure_ascii=False),
                            "running",
                            embed_started,
                            "medium",
                            "Generating embeddings...",
                        ),
                    )
                    tool_run_id_fk = embed_tool_run_id
                except Exception as exc:
                    print(f"CRITICAL: Failed to insert tool_run {embed_tool_run_id}: {exc}", flush=True)
                    embed_errors.append(f"tool_run_insert_failed: {exc}")
                    # Fallback: persist without ingest_batch_id if the FK is blocking.
                    try:
                        _db_execute(
                            """
                            INSERT INTO tool_runs (
                              id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
                              started_at, ended_at, confidence_hint, uncertainty_note
                            )
                            VALUES (%s, NULL, %s, %s::jsonb, %s::jsonb, %s, %s, null, %s, %s)
                            """,
                            (
                                embed_tool_run_id,
                                "embed_chunks",
                                json.dumps(
                                    {
                                        "chunk_count": len(chunks_to_embed),
                                        "model_id": embed_model_id,
                                        "embeddings_base_url": os.environ.get("TPA_EMBEDDINGS_BASE_URL"),
                                        "model_supervisor_url": os.environ.get("TPA_MODEL_SUPERVISOR_URL"),
                                    },
                                    ensure_ascii=False,
                                ),
                                json.dumps({}, ensure_ascii=False),
                                "running",
                                embed_started,
                                "medium",
                                "Generating embeddings (ingest batch unknown).",
                            ),
                        )
                        tool_run_id_fk = embed_tool_run_id
                    except Exception as exc2:
                        embed_errors.append(f"tool_run_insert_failed_fallback_null_ingest_batch: {exc2}")
                        tool_run_id_fk = None

                # Verify tool_run exists
                if tool_run_id_fk and (not _db_fetch_one("SELECT 1 FROM tool_runs WHERE id = %s::uuid", (embed_tool_run_id,))):
                    print(f"CRITICAL: tool_run {embed_tool_run_id} not found after insert!", flush=True)
                    embed_errors.append("tool_run_not_persisted")
                    tool_run_id_fk = None

                try:
                    batch_size = int(os.environ.get("TPA_INGEST_EMBED_BATCH_SIZE", "96"))
                except Exception:  # noqa: BLE001
                    batch_size = 96
                batch_size = max(8, min(batch_size, 256))

                for i in range(0, len(chunks_to_embed), batch_size):
                    batch = chunks_to_embed[i : i + batch_size]
                    embeddings = _embed_texts_sync(texts=[t for _, t in batch], model_id=embed_model_id)

                    if embeddings and len(embeddings) == len(batch):
                        for (chunk_id, _), vec in zip(batch, embeddings, strict=True):
                            try:
                                _db_execute(
                                    """
                                    INSERT INTO chunk_embeddings (
                                      id, chunk_id, embedding, embedding_model_id, created_at, tool_run_id
                                    )
                                    VALUES (%s, %s, %s::vector, %s, %s, %s::uuid)
                                    ON CONFLICT (chunk_id, embedding_model_id) DO NOTHING
                                    """,
                                    (
                                        str(uuid4()),
                                        chunk_id,
                                        _vector_literal(vec),
                                        embed_model_id,
                                        _utc_now(),
                                        tool_run_id_fk,
                                    ),
                                )
                                inserted += 1
                            except Exception as exc:  # noqa: BLE001
                                embed_errors.append(str(exc))
                    else:
                        embed_errors.append(f"embeddings_unavailable_or_failed_batch_{i//batch_size}")

                embed_ended = _utc_now()
                status_final = "success" if (inserted > 0 and not embed_errors) else ("partial" if inserted > 0 else "error")

                if tool_run_id_fk:
                    _db_execute(
                        """
                        UPDATE tool_runs
                        SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                            confidence_hint = %s, uncertainty_note = %s
                        WHERE id = %s
                        """,
                        (
                            status_final,
                            json.dumps(
                                {
                                    "inserted": inserted,
                                    "embedding_dim": len(embeddings[0])
                                    if (inserted > 0 and "embeddings" in locals() and embeddings)
                                    else None,
                                    "errors": embed_errors[:20],
                                },
                                ensure_ascii=False,
                            ),
                            embed_ended,
                            "medium" if inserted > 0 else "low",
                            (
                                "Embeddings generated for retrieval; model-dependent and not a determination of relevance."
                                if inserted > 0
                                else "Chunk embeddings were not generated; start the embeddings service (or enable the model supervisor) and re-run embedding."
                            ),
                            embed_tool_run_id,
                        ),
                    )

                if inserted == 0:
                    errors.append("Chunk embeddings were not generated (embeddings service unavailable or failed).")
                counts["chunk_embeddings_inserted"] += inserted

            # Policy extraction is an instrument: LLM clause parse + modality tags are persisted for downstream reasoning.
            if not phased:
                try:
                    doc_title = str(doc.get("title") or src_path.stem)
                    extracted = _extract_policies_from_document_chunks(
                        authority_id=authority_id,
                        plan_cycle_id=plan_cycle_id,
                        ingest_batch_id=ingest_batch_id,
                        document_id=document_id,
                        document_title=doc_title,
                        plan_cycle_status=plan_cycle_row.get("status"),
                        plan_cycle_weight_hint=plan_cycle_row.get("weight_hint"),
                        effective_from=plan_cycle_row.get("effective_from"),
                        effective_to=plan_cycle_row.get("effective_to"),
                    )
                    counts["policies_created"] += int(extracted.get("policies_created") or 0)
                    counts["policy_clauses_created"] += int(extracted.get("policy_clauses_created") or 0)
                    counts["policy_clause_embeddings_inserted"] += int(extracted.get("embeddings_inserted") or 0)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"Policy clause extraction failed for {src_path.name}: {exc}")

        if phased:
            # --- Phase 2: Policy extraction (LLM instrument; runs without embeddings to avoid GPU model ping-pong)
            _update_ingest_batch_progress(
                ingest_batch_id=ingest_batch_id,
                status="running",
                counts=counts,
                errors=errors,
                document_ids=document_ids,
                plan_cycle_id=plan_cycle_id,
                progress={"phase": "policy_extraction", "current_document": None, "phased": phased},
            )
            for d in docs_for_postprocessing:
                rel = str(d.get("source_rel_path") or "")
                _update_ingest_batch_progress(
                    ingest_batch_id=ingest_batch_id,
                    status="running",
                    counts=counts,
                    errors=errors,
                    document_ids=document_ids,
                    plan_cycle_id=plan_cycle_id,
                    progress={"phase": "policy_extraction", "current_document": rel or None, "phased": phased},
                )
                try:
                    extracted = _extract_policies_from_document_chunks(
                        authority_id=authority_id,
                        plan_cycle_id=plan_cycle_id,
                        ingest_batch_id=ingest_batch_id,
                        document_id=str(d["document_id"]),
                        document_title=str(d.get("document_title") or ""),
                        plan_cycle_status=plan_cycle_row.get("status"),
                        plan_cycle_weight_hint=plan_cycle_row.get("weight_hint"),
                        effective_from=plan_cycle_row.get("effective_from"),
                        effective_to=plan_cycle_row.get("effective_to"),
                        embed_policy_clause_embeddings=False,
                    )
                    counts["policies_created"] += int(extracted.get("policies_created") or 0)
                    counts["policy_clauses_created"] += int(extracted.get("policy_clauses_created") or 0)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"Policy clause extraction failed for {d.get('source_name') or rel or d.get('document_id')}: {exc}")

            # --- Phase 3: Embeddings (chunks + policy clauses) (EmbeddingProvider; single GPU model role)
            embed_model_id = os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B")
            try:
                batch_size = int(os.environ.get("TPA_INGEST_EMBED_BATCH_SIZE", "96"))
            except Exception:  # noqa: BLE001
                batch_size = 96
            batch_size = max(8, min(batch_size, 256))

            # 3a) Chunk embeddings (backfill across plan cycle)
            missing_chunks = _db_fetch_all(
                """
                SELECT c.id AS chunk_id, LEFT(c.text, 4000) AS text
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                LEFT JOIN chunk_embeddings ce
                  ON ce.chunk_id = c.id AND ce.embedding_model_id = %s
                WHERE d.authority_id = %s
                  AND d.plan_cycle_id = %s::uuid
                  AND d.is_active = true
                  AND ce.id IS NULL
                ORDER BY c.page_number ASC NULLS LAST, (c.metadata->>'evidence_ref_fragment') ASC NULLS LAST
                """,
                (embed_model_id, authority_id, plan_cycle_id),
            )
            chunks_to_embed = [(str(r["chunk_id"]), str(r.get("text") or "")) for r in missing_chunks if r.get("chunk_id")]
            chunks_to_embed = [(cid, t) for cid, t in chunks_to_embed if t.strip()]
            if chunks_to_embed:
                _update_ingest_batch_progress(
                    ingest_batch_id=ingest_batch_id,
                    status="running",
                    counts=counts,
                    errors=errors,
                    document_ids=document_ids,
                    plan_cycle_id=plan_cycle_id,
                    progress={
                        "phase": "embeddings_chunks",
                        "current_document": None,
                        "phased": phased,
                        "total": len(chunks_to_embed),
                        "done": 0,
                    },
                )
                embed_tool_run_id = str(uuid4())
                embed_started = _utc_now()
                embed_errors: list[str] = []
                inserted = 0
                tool_run_id_fk: str | None = None

                # IMPORTANT: insert the ToolRun before inserting embeddings, otherwise FK checks fail.
                try:
                    _db_execute(
                        """
                        INSERT INTO tool_runs (
                          id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
                          started_at, ended_at, confidence_hint, uncertainty_note
                        )
                        VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, null, %s, %s)
                        """,
                        (
                            embed_tool_run_id,
                            ingest_batch_id,
                            "embed_chunks",
                            json.dumps(
                                {
                                    "chunk_count": len(chunks_to_embed),
                                    "model_id": embed_model_id,
                                    "mode": "batch_plan_cycle_backfill",
                                    "embeddings_base_url": os.environ.get("TPA_EMBEDDINGS_BASE_URL"),
                                    "model_supervisor_url": os.environ.get("TPA_MODEL_SUPERVISOR_URL"),
                                },
                                ensure_ascii=False,
                            ),
                            json.dumps({}, ensure_ascii=False),
                            "running",
                            embed_started,
                            "medium",
                            "Generating embeddings...",
                        ),
                    )
                    tool_run_id_fk = embed_tool_run_id
                except Exception as exc:  # noqa: BLE001
                    # Still attempt to compute embeddings, but omit tool_run_id to avoid FK failures.
                    embed_errors.append(f"tool_run_insert_failed: {exc}")

                for i in range(0, len(chunks_to_embed), batch_size):
                    batch = chunks_to_embed[i : i + batch_size]
                    embeddings = _embed_texts_sync(texts=[t for _, t in batch], model_id=embed_model_id, time_budget_seconds=120.0)
                    if not embeddings or len(embeddings) != len(batch):
                        embed_errors.append(f"embeddings_unavailable_or_failed_batch_{i//batch_size}")
                        continue
                    for (chunk_id, _), vec in zip(batch, embeddings, strict=True):
                        try:
                            _db_execute(
                                """
                                INSERT INTO chunk_embeddings (
                                  id, chunk_id, embedding, embedding_model_id, created_at, tool_run_id
                                )
                                VALUES (%s, %s, %s::vector, %s, %s, %s::uuid)
                                ON CONFLICT (chunk_id, embedding_model_id) DO NOTHING
                                """,
                                (str(uuid4()), chunk_id, _vector_literal(vec), embed_model_id, _utc_now(), tool_run_id_fk),
                            )
                            inserted += 1
                        except Exception as exc:  # noqa: BLE001
                            embed_errors.append(str(exc))
                    _update_ingest_batch_progress(
                        ingest_batch_id=ingest_batch_id,
                        status="running",
                        counts=counts,
                        errors=errors,
                        document_ids=document_ids,
                        plan_cycle_id=plan_cycle_id,
                        progress={
                            "phase": "embeddings_chunks",
                            "current_document": None,
                            "phased": phased,
                            "total": len(chunks_to_embed),
                            "done": min(i + len(batch), len(chunks_to_embed)),
                        },
                    )

                embed_ended = _utc_now()
                status_final = "success" if (inserted > 0 and not embed_errors) else ("partial" if inserted > 0 else "error")
                outputs_logged = {"inserted": inserted, "errors": embed_errors[:20]}
                confidence_hint = "medium" if inserted > 0 else "low"
                uncertainty_note = (
                    "Embeddings generated for retrieval; model-dependent and not a determination of relevance."
                    if inserted > 0
                    else "Chunk embeddings were not generated; start the embeddings service (or enable the model supervisor) and re-run embedding."
                )
                if tool_run_id_fk:
                    _db_execute(
                        """
                        UPDATE tool_runs
                        SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                            confidence_hint = %s, uncertainty_note = %s
                        WHERE id = %s
                        """,
                        (
                            status_final,
                            json.dumps(outputs_logged, ensure_ascii=False),
                            embed_ended,
                            confidence_hint,
                            uncertainty_note,
                            embed_tool_run_id,
                        ),
                    )

                if inserted == 0:
                    errors.append("Chunk embeddings were not generated (embeddings service unavailable or failed).")
                counts["chunk_embeddings_inserted"] += inserted

            # 3b) Policy clause embeddings (if policies exist)
            missing_clauses = _db_fetch_all(
                """
                SELECT pc.id AS clause_id, LEFT(pc.text, 4000) AS text
                FROM policy_clauses pc
                JOIN policies p ON p.id = pc.policy_id
                LEFT JOIN policy_clause_embeddings pce
                  ON pce.policy_clause_id = pc.id AND pce.embedding_model_id = %s
                WHERE p.authority_id = %s
                  AND p.plan_cycle_id = %s::uuid
                  AND p.is_active = true
                  AND pce.id IS NULL
                ORDER BY pc.id ASC
                """,
                (embed_model_id, authority_id, plan_cycle_id),
            )
            clauses_to_embed = [(str(r["clause_id"]), str(r.get("text") or "")) for r in missing_clauses if r.get("clause_id")]
            clauses_to_embed = [(cid, t) for cid, t in clauses_to_embed if t.strip()]
            if clauses_to_embed:
                _update_ingest_batch_progress(
                    ingest_batch_id=ingest_batch_id,
                    status="running",
                    counts=counts,
                    errors=errors,
                    document_ids=document_ids,
                    plan_cycle_id=plan_cycle_id,
                    progress={
                        "phase": "embeddings_policy_clauses",
                        "current_document": None,
                        "phased": phased,
                        "total": len(clauses_to_embed),
                        "done": 0,
                    },
                )
                embed_tool_run_id = str(uuid4())
                embed_started = _utc_now()
                embed_errors: list[str] = []
                inserted = 0
                tool_run_id_fk: str | None = None

                # Insert tool_run first to satisfy FK
                try:
                    _db_execute(
                        """
                        INSERT INTO tool_runs (
                          id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status,
                          started_at, ended_at, confidence_hint, uncertainty_note
                        )
                        VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, null, %s, %s)
                        """,
                        (
                            embed_tool_run_id,
                            ingest_batch_id,
                            "embed_policy_clauses",
                            json.dumps({"model_id": embed_model_id, "clause_count": len(clauses_to_embed)}, ensure_ascii=False),
                            json.dumps({}, ensure_ascii=False),
                            "running",
                            embed_started,
                            "medium",
                            "Generating policy embeddings...",
                        ),
                    )
                    tool_run_id_fk = embed_tool_run_id
                except Exception as exc:
                    print(f"CRITICAL: Failed to insert tool_run {embed_tool_run_id}: {exc}", flush=True)
                    embed_errors.append(f"tool_run_insert_failed: {exc}")

                # Verify tool_run exists
                if tool_run_id_fk and (not _db_fetch_one("SELECT 1 FROM tool_runs WHERE id = %s::uuid", (embed_tool_run_id,))):
                    print(f"CRITICAL: tool_run {embed_tool_run_id} not found after insert!", flush=True)
                    embed_errors.append("tool_run_not_persisted")
                    tool_run_id_fk = None

                for i in range(0, len(clauses_to_embed), batch_size):
                    batch = clauses_to_embed[i : i + batch_size]
                    embeddings = _embed_texts_sync(texts=[t for _, t in batch], model_id=embed_model_id, time_budget_seconds=120.0)
                    if not embeddings or len(embeddings) != len(batch):
                        embed_errors.append(f"embeddings_unavailable_or_failed_batch_{i//batch_size}")
                        continue
                    for (clause_id, _), vec in zip(batch, embeddings, strict=True):
                        try:
                            _db_execute(
                                """
                                INSERT INTO policy_clause_embeddings (
                                  id, policy_clause_id, embedding, embedding_model_id, created_at, tool_run_id
                                )
                                VALUES (%s, %s::uuid, %s::vector, %s, %s, %s::uuid)
                                ON CONFLICT (policy_clause_id, embedding_model_id) DO NOTHING
                                """,
                                (str(uuid4()), clause_id, _vector_literal(vec), embed_model_id, _utc_now(), tool_run_id_fk),
                            )
                            inserted += 1
                        except Exception as exc:  # noqa: BLE001
                            embed_errors.append(str(exc))
                    _update_ingest_batch_progress(
                        ingest_batch_id=ingest_batch_id,
                        status="running",
                        counts=counts,
                        errors=errors,
                        document_ids=document_ids,
                        plan_cycle_id=plan_cycle_id,
                        progress={
                            "phase": "embeddings_policy_clauses",
                            "current_document": None,
                            "phased": phased,
                            "total": len(clauses_to_embed),
                            "done": min(i + len(batch), len(clauses_to_embed)),
                        },
                    )

                embed_ended = _utc_now()
                status_final = "success" if (inserted > 0 and not embed_errors) else ("partial" if inserted > 0 else "error")

                if tool_run_id_fk:
                    _db_execute(
                        """
                        UPDATE tool_runs
                        SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                            confidence_hint = %s, uncertainty_note = %s
                        WHERE id = %s
                        """,
                        (
                            status_final,
                            json.dumps({"inserted": inserted, "errors": embed_errors[:20]}, ensure_ascii=False),
                            embed_ended,
                            "medium" if inserted > 0 else "low",
                            (
                                "Embeddings support clause-aware retrieval; not a determination of policy weight or relevance."
                                if inserted > 0
                                else "Policy clause embeddings were not generated; start the embeddings service (or enable the model supervisor)."
                            ),
                            embed_tool_run_id,
                        ),
                    )

                if inserted == 0:
                    errors.append("Policy clause embeddings were not generated (embeddings service unavailable or failed).")
                counts["policy_clause_embeddings_inserted"] += inserted

        status = "success" if not errors else "partial"
    except HTTPException as exc:
        errors.append(str(exc.detail))
        status = "failed"
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Unhandled error: {exc}")
        status = "failed"
    finally:
        ended_at = _utc_now()
        outputs = {
            "counts": counts,
            "errors": errors[:50],
            "document_ids": document_ids[:200],
            "plan_cycle_id": plan_cycle_id,
        }

        for tmp_path in temp_paths:
            try:
                tmp_path.unlink()
            except Exception:  # noqa: BLE001
                pass
            try:
                tmp_path.parent.rmdir()
            except Exception:  # noqa: BLE001
                pass

        try:
            _db_execute(
                """
                INSERT INTO tool_runs (
                  id, ingest_batch_id, tool_name, inputs_logged, outputs_logged,
                  status, started_at, ended_at, confidence_hint, uncertainty_note
                )
                VALUES (%s, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
                """,
                (
                    tool_run_id,
                    ingest_batch_id,
                    "ingest_authority_pack",
                    json.dumps({"authority_id": authority_id, "plan_cycle_id": plan_cycle_id}, ensure_ascii=False),
                    json.dumps(outputs, ensure_ascii=False),
                    status,
                    started_at,
                    ended_at,
                    "medium",
                    "Extracted PDF text per page and ran an LLM policy parse instrument to derive clause fragments (non-deterministic; persisted with provenance).",
                ),
            )
        except Exception:  # noqa: BLE001
            pass

        try:
            _db_execute(
                """
                UPDATE ingest_batches
                SET completed_at = %s, status = %s, outputs_jsonb = %s::jsonb
                WHERE id = %s::uuid
                """,
                (ended_at, status, json.dumps(outputs, ensure_ascii=False), ingest_batch_id),
            )
        except Exception:  # noqa: BLE001
            pass

        try:
            _audit_event(
                event_type="authority_pack_ingested",
                actor_type="system",
                payload={
                    "authority_id": authority_id,
                    "plan_cycle_id": plan_cycle_id,
                    "ingest_batch_id": ingest_batch_id,
                    "tool_run_id": tool_run_id,
                    "counts": counts,
                    "errors": errors[:10],
                },
            )
        except Exception:  # noqa: BLE001
            pass

    return {
        "authority_id": authority_id,
        "plan_cycle_id": plan_cycle_id,
        "ingest_batch_id": ingest_batch_id,
        "tool_run_id": tool_run_id,
        "status": status,
        "counts": counts,
        "errors": errors,
    }


def _create_ingest_job(
    *,
    authority_id: str,
    plan_cycle_id: str,
    ingest_batch_id: str,
    job_type: str,
    inputs: dict[str, Any],
) -> str:
    job_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO ingest_jobs (
          id, ingest_batch_id, authority_id, plan_cycle_id, job_type, status,
          inputs_jsonb, outputs_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s, %s::uuid, %s, %s, %s::jsonb, %s::jsonb, %s)
        """,
        (
            job_id,
            ingest_batch_id,
            authority_id,
            plan_cycle_id,
            job_type,
            "pending",
            json.dumps(inputs, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
            _utc_now(),
        ),
    )
    return job_id


def _enqueue_ingest_job(job_id: str) -> tuple[bool, str | None]:
    try:
        from ..ingest_worker import celery_app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return False, f"celery_import_failed:{exc}"
    try:
        celery_app.send_task("tpa_api.ingest_worker.process_ingest_job", args=[job_id])
    except Exception as exc:  # noqa: BLE001
        return False, f"celery_enqueue_failed:{exc}"
    return True, None


def start_ingest_authority_pack(authority_id: str, body: AuthorityPackIngestRequest | None = None) -> JSONResponse:
    body = body or AuthorityPackIngestRequest()

    pack_dir = _authority_packs_root() / authority_id
    if not pack_dir.exists():
        raise HTTPException(status_code=404, detail=f"Authority pack not found: {authority_id}")

    manifest = _load_authority_pack_manifest(authority_id)
    documents = _normalize_authority_pack_documents(manifest)
    if not documents:
        raise HTTPException(status_code=400, detail=f"No documents listed in authority pack manifest for '{authority_id}'")

    # If a run is already in-flight for this authority+cycle, return it.
    if body.plan_cycle_id:
        body.plan_cycle_id = _validate_uuid_or_400(body.plan_cycle_id, field_name="plan_cycle_id")
        existing = _db_fetch_one(
            """
            SELECT id
            FROM ingest_batches
            WHERE authority_id = %s
              AND plan_cycle_id = %s::uuid
              AND status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (authority_id, body.plan_cycle_id),
        )
        if existing:
            ingest_batch_id = str(existing["id"])
            return JSONResponse(
                status_code=202,
                content=jsonable_encoder(
                    {
                        "authority_id": authority_id,
                        "plan_cycle_id": body.plan_cycle_id,
                        "ingest_batch_id": ingest_batch_id,
                        "status": "running",
                        "message": "Ingest already running for this plan cycle.",
                    }
                ),
            )

    plan_cycle_row, plan_cycle_id, ingest_batch_id, tool_run_id, started_at = _prepare_authority_pack_ingest(
        authority_id=authority_id,
        body=body,
        manifest=manifest,
        document_count=len(documents),
    )
    ingest_job_id = _create_ingest_job(
        authority_id=authority_id,
        plan_cycle_id=plan_cycle_id,
        ingest_batch_id=ingest_batch_id,
        job_type="authority_pack",
        inputs={
            "authority_id": authority_id,
            "plan_cycle_id": plan_cycle_id,
            "pack_dir": str(pack_dir),
            "documents": documents,
            "manifest": {"id": manifest.get("id"), "name": manifest.get("name")},
        },
    )
    enqueued, enqueue_error = _enqueue_ingest_job(ingest_job_id)
    if not enqueued:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue ingest job: {enqueue_error}")

    _audit_event(
        event_type="authority_pack_ingest_queued",
        actor_type="system",
        payload={
            "authority_id": authority_id,
            "plan_cycle_id": plan_cycle_id,
            "ingest_batch_id": ingest_batch_id,
            "ingest_job_id": ingest_job_id,
        },
    )

    return JSONResponse(
        status_code=202,
        content=jsonable_encoder(
            {
                "authority_id": authority_id,
                "plan_cycle_id": plan_cycle_id,
                "ingest_batch_id": ingest_batch_id,
                "ingest_job_id": ingest_job_id,
                "tool_run_id": tool_run_id,
                "status": "queued",
                "message": "Ingest job queued.",
            }
        ),
    )


def ingest_authority_pack(authority_id: str, body: AuthorityPackIngestRequest | None = None) -> JSONResponse:
    body = body or AuthorityPackIngestRequest()
    return start_ingest_authority_pack(authority_id, body)


def list_ingest_batches(
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    limit: int = 25,
) -> JSONResponse:
    limit = max(1, min(int(limit), 200))
    where: list[str] = []
    params: list[Any] = []
    if authority_id:
        where.append("authority_id = %s")
        params.append(authority_id)
    if plan_cycle_id:
        where.append("plan_cycle_id = %s::uuid")
        params.append(plan_cycle_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = _db_fetch_all(
        f"""
        SELECT
          id, source_system, authority_id, plan_cycle_id,
          started_at, completed_at, status, notes, inputs_jsonb, outputs_jsonb
        FROM ingest_batches
        {where_sql}
        ORDER BY started_at DESC
        LIMIT %s
        """,
        tuple(params + [limit]),
    )
    items = [
        {
            "ingest_batch_id": str(r["id"]),
            "source_system": r["source_system"],
            "authority_id": r["authority_id"],
            "plan_cycle_id": str(r["plan_cycle_id"]) if r["plan_cycle_id"] else None,
            "started_at": r["started_at"],
            "completed_at": r["completed_at"],
            "status": r["status"],
            "notes": r["notes"],
            "inputs": r["inputs_jsonb"] or {},
            "outputs": r["outputs_jsonb"] or {},
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"ingest_batches": items}))


def list_ingest_jobs(
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> JSONResponse:
    limit = max(1, min(int(limit), 200))
    where: list[str] = []
    params: list[Any] = []
    if authority_id:
        where.append("authority_id = %s")
        params.append(authority_id)
    if plan_cycle_id:
        where.append("plan_cycle_id = %s::uuid")
        params.append(plan_cycle_id)
    if status:
        where.append("status = %s")
        params.append(status)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = _db_fetch_all(
        f"""
        SELECT id, ingest_batch_id, authority_id, plan_cycle_id, job_type, status,
               inputs_jsonb, outputs_jsonb, created_at, started_at, completed_at, error_text
        FROM ingest_jobs
        {where_sql}
        ORDER BY created_at DESC
        LIMIT %s
        """,
        tuple(params + [limit]),
    )
    jobs = [
        {
            "ingest_job_id": str(r["id"]),
            "ingest_batch_id": str(r["ingest_batch_id"]) if r.get("ingest_batch_id") else None,
            "authority_id": r.get("authority_id"),
            "plan_cycle_id": str(r["plan_cycle_id"]) if r.get("plan_cycle_id") else None,
            "job_type": r.get("job_type"),
            "status": r.get("status"),
            "inputs": r.get("inputs_jsonb") or {},
            "outputs": r.get("outputs_jsonb") or {},
            "created_at": r.get("created_at"),
            "started_at": r.get("started_at"),
            "completed_at": r.get("completed_at"),
            "error_text": r.get("error_text"),
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"ingest_jobs": jobs}))


def get_ingest_job(ingest_job_id: str) -> JSONResponse:
    row = _db_fetch_one(
        """
        SELECT id, ingest_batch_id, authority_id, plan_cycle_id, job_type, status,
               inputs_jsonb, outputs_jsonb, created_at, started_at, completed_at, error_text
        FROM ingest_jobs
        WHERE id = %s::uuid
        """,
        (ingest_job_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Ingest job not found")

    return JSONResponse(
        content=jsonable_encoder(
            {
                "ingest_job": {
                    "ingest_job_id": str(row["id"]),
                    "ingest_batch_id": str(row["ingest_batch_id"]) if row.get("ingest_batch_id") else None,
                    "authority_id": row.get("authority_id"),
                    "plan_cycle_id": str(row["plan_cycle_id"]) if row.get("plan_cycle_id") else None,
                    "job_type": row.get("job_type"),
                    "status": row.get("status"),
                    "inputs": row.get("inputs_jsonb") or {},
                    "outputs": row.get("outputs_jsonb") or {},
                    "created_at": row.get("created_at"),
                    "started_at": row.get("started_at"),
                    "completed_at": row.get("completed_at"),
                    "error_text": row.get("error_text"),
                }
            }
        )
    )


def get_ingest_batch(ingest_batch_id: str) -> JSONResponse:
    row = _db_fetch_one(
        """
        SELECT
          id, source_system, authority_id, plan_cycle_id,
          started_at, completed_at, status, notes, inputs_jsonb, outputs_jsonb
        FROM ingest_batches
        WHERE id = %s::uuid
        """,
        (ingest_batch_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Ingest batch not found")

    tool_runs = _db_fetch_all(
        """
        SELECT id, tool_name, status, started_at, ended_at, confidence_hint, uncertainty_note
        FROM tool_runs
        WHERE ingest_batch_id = %s::uuid
        ORDER BY started_at ASC
        """,
        (ingest_batch_id,),
    )

    return JSONResponse(
        content=jsonable_encoder(
            {
                "ingest_batch": {
                    "ingest_batch_id": str(row["id"]),
                    "source_system": row["source_system"],
                    "authority_id": row["authority_id"],
                    "plan_cycle_id": str(row["plan_cycle_id"]) if row["plan_cycle_id"] else None,
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "status": row["status"],
                    "notes": row["notes"],
                    "inputs": row["inputs_jsonb"] or {},
                    "outputs": row["outputs_jsonb"] or {},
                    "tool_runs": [
                        {
                            "tool_run_id": str(t["id"]),
                            "tool_name": t["tool_name"],
                            "status": t["status"],
                            "started_at": t["started_at"],
                            "ended_at": t["ended_at"],
                            "confidence_hint": t["confidence_hint"],
                            "uncertainty_note": t["uncertainty_note"],
                        }
                        for t in tool_runs
                    ],
                }
            }
        )
    )
