from __future__ import annotations

import json
import os
import re
import mimetypes
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from datetime import date, datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from psycopg import errors as pg_errors

from .api_utils import validate_uuid_or_400 as _validate_uuid_or_400
from .blob_store import minio_client_or_none as _minio_client_or_none
from .context_assembly import ContextAssemblyDeps, assemble_curated_evidence_set_sync
from .chunking import _semantic_chunk_lines
from .db import _db_execute, _db_execute_returning, _db_fetch_all, _db_fetch_one, init_db_pool, shutdown_db_pool
from .evidence import _ensure_evidence_ref_row, _parse_evidence_ref
from .model_clients import (
    _embed_texts,
    _embed_texts_sync,
    _ensure_model_role,
    _ensure_model_role_sync,
    _llm_model_id,
    _rerank_texts_sync,
    _vlm_model_id,
)
from .prompting import _llm_structured_sync
from .retrieval import _gather_draft_evidence, _retrieve_chunks_hybrid_sync, _retrieve_policy_clauses_hybrid_sync
from .spec_io import _read_json, _read_yaml, _spec_root
from .text_utils import _extract_json_object
from .time_utils import _utc_now, _utc_now_iso
from .tool_requests import persist_tool_requests_for_move
from .vector_utils import _vector_literal
from .routes.retrieval_frames import router as retrieval_frames_router
from .routes.tool_requests import router as tool_requests_router


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
        title = rest.lstrip(": -–—").strip() or None
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
                elif isinstance(data.get("pages"), list):
                    for item in data["pages"]:
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


app = FastAPI(title="TPA API (Scaffold)", version="0.0.0")


@app.on_event("startup")
def _startup_db_pool() -> None:
    init_db_pool()


@app.on_event("shutdown")
def _shutdown_db_pool() -> None:
    shutdown_db_pool()

app.include_router(retrieval_frames_router)
app.include_router(tool_requests_router)


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


def _normalize_authority_pack_documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw = manifest.get("documents", [])
    if raw is None:
        return []
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        return [{"file_path": x, "title": Path(x).stem, "source": "authority_pack"} for x in raw]
    if isinstance(raw, list) and all(isinstance(x, dict) for x in raw):
        out: list[dict[str, Any]] = []
        for d in raw:
            fp = d.get("file_path") or d.get("path") or d.get("file")
            if not fp:
                continue
            out.append(
                {
                    "file_path": fp,
                    "title": d.get("title") or Path(str(fp)).stem,
                    "document_type": d.get("type") or d.get("document_type"),
                    "source": d.get("source") or "authority_pack",
                    "published_date": d.get("published_date") or d.get("date"),
                }
            )
        return out
    return []


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/spec/culp/process-model")
def culp_process_model() -> JSONResponse:
    root = _spec_root()
    model_path = root / "culp" / "PROCESS_MODEL.yaml"
    return JSONResponse(content=_read_yaml(model_path))


@app.get("/spec/culp/artefact-registry")
def culp_artefact_registry() -> JSONResponse:
    root = _spec_root()
    registry_path = root / "culp" / "ARTEFACT_REGISTRY.yaml"
    return JSONResponse(content=_read_yaml(registry_path))


@app.get("/spec/authorities/selected")
def selected_authorities() -> JSONResponse:
    root = _spec_root()
    selected_path = root / "authorities" / "SELECTED_AUTHORITIES.yaml"
    return JSONResponse(content=_read_yaml(selected_path))


@app.get("/spec/framing/political-framings")
def political_framings() -> JSONResponse:
    root = _spec_root()
    framings_path = root / "framing" / "POLITICAL_FRAMINGS.yaml"
    return JSONResponse(content=_read_yaml(framings_path))


async def _llm_blocks(
    *,
    draft_request: dict[str, Any],
    time_budget_seconds: float,
    evidence_context: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    base_url = await _ensure_model_role(role="llm", timeout_seconds=180.0) or os.environ.get("TPA_LLM_BASE_URL")
    if not base_url:
        return None

    model = _llm_model_id()
    timeout = min(max(time_budget_seconds, 1.0), 60.0)

    system = (
        "You are The Planner's Assistant. Produce a quick first draft for a UK planning professional. "
        "You will be given an evidence_context list. When you make factual claims, cite relevant evidence "
        "by including EvidenceRef strings in an 'evidence_refs' array per block. "
        "Return ONLY valid JSON with this shape: "
        "{ \"blocks\": [ {\"block_type\": \"heading|paragraph|bullets|callout|other\", \"content\": string, "
        "\"evidence_refs\": string[], \"requires_judgement_run\": boolean } ] }. "
        "Keep it concise and useful. Do not include markdown fences."
    )
    user = json.dumps({"draft_request": draft_request, "evidence_context": evidence_context or []}, ensure_ascii=False)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
        "max_tokens": 900,
    }

    url = base_url.rstrip("/") + "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return None

    obj = _extract_json_object(content)
    if not obj:
        return None
    blocks = obj.get("blocks")
    if not isinstance(blocks, list):
        return None
    cleaned: list[dict[str, Any]] = []
    for b in blocks[:8]:
        if not isinstance(b, dict):
            continue
        block_type = b.get("block_type")
        content_text = b.get("content")
        evidence_refs = b.get("evidence_refs")
        requires = b.get("requires_judgement_run")
        if block_type not in {"heading", "paragraph", "bullets", "callout", "other"}:
            continue
        if not isinstance(content_text, str) or not content_text.strip():
            continue
        if not isinstance(evidence_refs, list):
            evidence_refs = []
        cleaned_refs = [r for r in evidence_refs if isinstance(r, str) and "::" in r][:10]
        if not isinstance(requires, bool):
            requires = False
        cleaned.append(
            {
                "block_type": block_type,
                "content": content_text.strip(),
                "evidence_refs": cleaned_refs,
                "requires_judgement_run": bool(requires),
            }
        )
    return cleaned or None


@app.post("/draft")
async def draft(request: dict[str, Any]) -> JSONResponse:
    required = ["draft_request_id", "requested_at", "requested_by", "artefact_type", "time_budget_seconds"]
    missing = [k for k in required if k not in request]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    artefact_type = request.get("artefact_type")
    time_budget_seconds = float(request.get("time_budget_seconds") or 10)

    constraints = request.get("constraints") if isinstance(request.get("constraints"), dict) else {}
    authority_id = constraints.get("authority_id") if isinstance(constraints.get("authority_id"), str) else None
    plan_cycle_id = constraints.get("plan_cycle_id") if isinstance(constraints.get("plan_cycle_id"), str) else None
    query_text = (request.get("user_prompt") or "") if isinstance(request.get("user_prompt"), str) else ""
    if not query_text.strip():
        query_text = str(artefact_type or "draft")
    evidence_context = (
        _gather_draft_evidence(authority_id=authority_id, plan_cycle_id=plan_cycle_id, query_text=query_text)
        if authority_id
        else []
    )

    llm_blocks = await _llm_blocks(
        draft_request=request,
        time_budget_seconds=time_budget_seconds,
        evidence_context=evidence_context,
    )
    if llm_blocks is None:
        llm_blocks = [
            {
                "block_type": "heading",
                "content": "Draft (starter)",
                "evidence_refs": [],
                "requires_judgement_run": False,
            },
            {
                "block_type": "paragraph",
                "content": (
                    "This is a quick draft starter intended for planner review. "
                    "Next: bind claims to evidence cards and run a judgement pass where needed."
                ),
                "evidence_refs": [],
                "requires_judgement_run": False,
            },
        ]

    suggestions: list[dict[str, Any]] = []
    for block in llm_blocks:
        suggestions.append(
            {
                "suggestion_id": str(uuid4()),
                "block_type": block["block_type"],
                "content": block["content"],
                "evidence_refs": block.get("evidence_refs", []) or [],
                "assumption_ids": [],
                "limitations_text": (
                    None
                    if block.get("requires_judgement_run") is False
                    else "Requires a full judgement run before sign-off."
                ),
                "requires_judgement_run": bool(block.get("requires_judgement_run")),
                "insertion_hint": {"artefact_type": artefact_type},
            }
        )

    pack = {
        "draft_pack_id": str(uuid4()),
        "draft_request_id": request["draft_request_id"],
        "status": "complete",
        "suggestions": suggestions,
        "tool_run_ids": [],
        "created_at": _utc_now_iso(),
    }
    return JSONResponse(content=pack)


@app.get("/spec/schemas")
def list_schemas() -> dict[str, list[str]]:
    root = _spec_root()
    schemas_dir = root / "schemas"
    if not schemas_dir.exists():
        raise HTTPException(status_code=404, detail="schemas directory missing in spec root")
    names = sorted(p.name for p in schemas_dir.glob("*.schema.json"))
    return {"schemas": names}


@app.get("/spec/schemas/{schema_name}")
def get_schema(schema_name: str) -> JSONResponse:
    if "/" in schema_name or ".." in schema_name:
        raise HTTPException(status_code=400, detail="Invalid schema name")
    root = _spec_root()
    schema_path = root / "schemas" / schema_name
    if not schema_path.name.endswith(".schema.json"):
        raise HTTPException(status_code=400, detail="Schema name must end with .schema.json")
    return JSONResponse(content=_read_json(schema_path))


def _audit_event(
    *,
    event_type: str,
    actor_type: str = "user",
    actor_id: str | None = None,
    run_id: str | None = None,
    plan_project_id: str | None = None,
    culp_stage_id: str | None = None,
    scenario_id: str | None = None,
    tool_run_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    _db_execute(
        """
        INSERT INTO audit_events (
          id, timestamp, event_type, actor_type, actor_id, run_id, plan_project_id,
          culp_stage_id, scenario_id, tool_run_id, payload_jsonb
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            str(uuid4()),
            _utc_now(),
            event_type,
            actor_type,
            actor_id,
            run_id,
            plan_project_id,
            culp_stage_id,
            scenario_id,
            tool_run_id,
            json.dumps(payload or {}, ensure_ascii=False),
        ),
    )


class PlanCycleCreate(BaseModel):
    authority_id: str
    plan_name: str
    status: str
    weight_hint: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    supersede_existing: bool = Field(
        default=False,
        description="If true, deactivate any conflicting active plan cycle(s) for this authority (sets is_active=false and superseded_by_cycle_id).",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.post("/plan-cycles")
def create_plan_cycle(body: PlanCycleCreate) -> JSONResponse:
    now = _utc_now()
    authority_id = (body.authority_id or "").strip()
    if not authority_id:
        raise HTTPException(status_code=400, detail="authority_id must not be empty")

    plan_name = (body.plan_name or "").strip() or "Plan cycle"
    status = _normalize_plan_cycle_status(body.status)
    weight_hint = (body.weight_hint or "").strip().lower() if isinstance(body.weight_hint, str) and body.weight_hint.strip() else None

    conflict_statuses = _plan_cycle_conflict_statuses(status)
    conflicts: list[dict[str, Any]] = []
    if conflict_statuses:
        placeholders = ",".join(["%s"] * len(conflict_statuses))
        conflicts = _db_fetch_all(
            f"""
            SELECT id, plan_name, status, weight_hint, updated_at
            FROM plan_cycles
            WHERE authority_id = %s
              AND is_active = true
              AND status IN ({placeholders})
            ORDER BY updated_at DESC
            """,
            tuple([authority_id, *conflict_statuses]),
        )
        if conflicts and not body.supersede_existing:
            existing_id = str(conflicts[0]["id"])
            raise HTTPException(
                status_code=409,
                detail=(
                    f"An active plan cycle already exists for authority '{authority_id}' with status in {set(conflict_statuses)} "
                    f"(e.g. {existing_id}). Update/deactivate it, or retry with supersede_existing=true."
                ),
            )

    new_id = str(uuid4())
    try:
        row = _db_execute_returning(
            """
            INSERT INTO plan_cycles (
              id, authority_id, plan_name, status, weight_hint, effective_from, effective_to,
              metadata_jsonb, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING
              id, authority_id, plan_name, status, weight_hint, effective_from, effective_to,
              superseded_by_cycle_id, is_active, metadata_jsonb, created_at, updated_at
            """,
            (
                new_id,
                authority_id,
                plan_name,
                status,
                weight_hint,
                body.effective_from,
                body.effective_to,
                json.dumps(body.metadata, ensure_ascii=False),
                now,
                now,
            ),
        )
    except pg_errors.UniqueViolation as exc:
        # DB-level guard for race conditions and non-UI clients.
        raise HTTPException(
            status_code=409,
            detail="Conflicting active plan cycle exists for this authority/status group. Deactivate it or supersede it.",
        ) from exc

    if conflicts and body.supersede_existing:
        for c in conflicts:
            try:
                _db_execute(
                    """
                    UPDATE plan_cycles
                    SET is_active = false, superseded_by_cycle_id = %s::uuid, updated_at = %s
                    WHERE id = %s::uuid
                    """,
                    (new_id, now, str(c["id"])),
                )
            except Exception:  # noqa: BLE001
                pass
        _audit_event(
            event_type="plan_cycle_superseded",
            payload={
                "authority_id": authority_id,
                "new_plan_cycle_id": new_id,
                "superseded_cycle_ids": [str(c["id"]) for c in conflicts],
            },
        )

    _audit_event(
        event_type="plan_cycle_created",
        payload={"plan_cycle_id": str(row["id"]), "authority_id": row["authority_id"], "status": row["status"]},
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "plan_cycle_id": str(row["id"]),
                "authority_id": row["authority_id"],
                "plan_name": row["plan_name"],
                "status": row["status"],
                "weight_hint": row["weight_hint"],
                "effective_from": row["effective_from"],
                "effective_to": row["effective_to"],
                "superseded_by_cycle_id": row["superseded_by_cycle_id"],
                "is_active": row["is_active"],
                "metadata": row["metadata_jsonb"] or {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    )


class PlanCyclePatch(BaseModel):
    status: str | None = None
    weight_hint: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    superseded_by_cycle_id: str | None = None
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None


@app.patch("/plan-cycles/{plan_cycle_id}")
def patch_plan_cycle(plan_cycle_id: str, body: PlanCyclePatch) -> JSONResponse:
    plan_cycle_id = _validate_uuid_or_400(plan_cycle_id, field_name="plan_cycle_id")
    existing = _db_fetch_one(
        "SELECT id, authority_id, status, is_active FROM plan_cycles WHERE id = %s::uuid",
        (plan_cycle_id,),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="plan_cycle_id not found")

    next_status = _normalize_plan_cycle_status(body.status) if body.status is not None else _normalize_plan_cycle_status(existing["status"])
    next_is_active = bool(body.is_active) if body.is_active is not None else bool(existing["is_active"])
    conflict_statuses = _plan_cycle_conflict_statuses(next_status)
    if next_is_active and conflict_statuses:
        placeholders = ",".join(["%s"] * len(conflict_statuses))
        conflict = _db_fetch_one(
            f"""
            SELECT id
            FROM plan_cycles
            WHERE authority_id = %s
              AND is_active = true
              AND status IN ({placeholders})
              AND id <> %s::uuid
            LIMIT 1
            """,
            tuple([existing["authority_id"], *conflict_statuses, plan_cycle_id]),
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot activate/set status to {set(conflict_statuses)}: another active plan cycle exists ({str(conflict['id'])}). "
                    "Deactivate/supersede it first."
                ),
            )

    now = _utc_now()
    try:
        row = _db_execute_returning(
            """
            UPDATE plan_cycles
            SET
              status = COALESCE(%s, status),
              weight_hint = COALESCE(%s, weight_hint),
              effective_from = COALESCE(%s, effective_from),
              effective_to = COALESCE(%s, effective_to),
              superseded_by_cycle_id = COALESCE(%s::uuid, superseded_by_cycle_id),
              is_active = COALESCE(%s, is_active),
              metadata_jsonb = COALESCE(%s::jsonb, metadata_jsonb),
              updated_at = %s
            WHERE id = %s::uuid
            RETURNING
              id, authority_id, plan_name, status, weight_hint, effective_from, effective_to,
              superseded_by_cycle_id, is_active, metadata_jsonb, created_at, updated_at
            """,
            (
                body.status,
                body.weight_hint,
                body.effective_from,
                body.effective_to,
                body.superseded_by_cycle_id,
                body.is_active,
                json.dumps(body.metadata, ensure_ascii=False) if body.metadata is not None else None,
                now,
                plan_cycle_id,
            ),
        )
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Conflicting active plan cycle exists for this authority/status group.") from exc
    _audit_event(
        event_type="plan_cycle_updated",
        payload={"plan_cycle_id": str(row["id"]), "changes": jsonable_encoder(body)},
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "plan_cycle_id": str(row["id"]),
                "authority_id": row["authority_id"],
                "plan_name": row["plan_name"],
                "status": row["status"],
                "weight_hint": row["weight_hint"],
                "effective_from": row["effective_from"],
                "effective_to": row["effective_to"],
                "superseded_by_cycle_id": row["superseded_by_cycle_id"],
                "is_active": row["is_active"],
                "metadata": row["metadata_jsonb"] or {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    )


@app.get("/plan-cycles")
def list_plan_cycles(authority_id: str | None = None, active_only: bool = True) -> JSONResponse:
    where: list[str] = []
    params: list[Any] = []
    if authority_id:
        where.append("authority_id = %s")
        params.append(authority_id)
    if active_only:
        where.append("is_active = true")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = _db_fetch_all(
        f"""
        SELECT
          id, authority_id, plan_name, status, weight_hint, effective_from, effective_to,
          superseded_by_cycle_id, is_active, metadata_jsonb, created_at, updated_at
        FROM plan_cycles
        {where_sql}
        ORDER BY updated_at DESC
        """,
        tuple(params),
    )
    items = [
        {
            "plan_cycle_id": str(r["id"]),
            "authority_id": r["authority_id"],
            "plan_name": r["plan_name"],
            "status": r["status"],
            "weight_hint": r["weight_hint"],
            "effective_from": r["effective_from"],
            "effective_to": r["effective_to"],
            "superseded_by_cycle_id": r["superseded_by_cycle_id"],
            "is_active": r["is_active"],
            "metadata": r["metadata_jsonb"] or {},
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"plan_cycles": items}))


class PlanProjectCreate(BaseModel):
    authority_id: str
    process_model_id: str
    title: str
    status: str = Field(default="draft")
    current_stage_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.post("/plan-projects")
def create_plan_project(body: PlanProjectCreate) -> JSONResponse:
    now = _utc_now()
    row = _db_execute_returning(
        """
        INSERT INTO plan_projects (
          id, authority_id, process_model_id, title, status, current_stage_id,
          metadata_jsonb, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
        RETURNING id, authority_id, process_model_id, title, status, current_stage_id, metadata_jsonb, created_at, updated_at
        """,
        (
            str(uuid4()),
            body.authority_id,
            body.process_model_id,
            body.title,
            body.status,
            body.current_stage_id,
            json.dumps(body.metadata, ensure_ascii=False),
            now,
            now,
        ),
    )
    _audit_event(
        event_type="plan_project_created",
        plan_project_id=str(row["id"]),
        payload={"authority_id": body.authority_id, "process_model_id": body.process_model_id},
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "plan_project_id": str(row["id"]),
                "authority_id": row["authority_id"],
                "process_model_id": row["process_model_id"],
                "title": row["title"],
                "status": row["status"],
                "current_stage_id": row["current_stage_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "metadata": row["metadata_jsonb"] or {},
            }
        )
    )


@app.get("/plan-projects")
def list_plan_projects(authority_id: str | None = None) -> JSONResponse:
    if authority_id:
        rows = _db_fetch_all(
            """
            SELECT id, authority_id, process_model_id, title, status, current_stage_id, metadata_jsonb, created_at, updated_at
            FROM plan_projects
            WHERE authority_id = %s
            ORDER BY updated_at DESC
            """,
            (authority_id,),
        )
    else:
        rows = _db_fetch_all(
            """
            SELECT id, authority_id, process_model_id, title, status, current_stage_id, metadata_jsonb, created_at, updated_at
            FROM plan_projects
            ORDER BY updated_at DESC
            """
        )
    items = [
        {
            "plan_project_id": str(r["id"]),
            "authority_id": r["authority_id"],
            "process_model_id": r["process_model_id"],
            "title": r["title"],
            "status": r["status"],
            "current_stage_id": r["current_stage_id"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "metadata": r["metadata_jsonb"] or {},
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"plan_projects": items}))


@app.get("/scenarios")
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


@app.get("/scenario-sets")
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


@app.post("/scenarios")
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


@app.post("/scenario-sets")
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


@app.get("/scenario-sets/{scenario_set_id}")
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
        SELECT id, scenario_set_id, scenario_id, political_framing_id, framing_id, run_id, status,
               trajectory_id, judgement_sheet_ref, updated_at
        FROM scenario_framing_tabs
        WHERE scenario_set_id = %s
        ORDER BY updated_at DESC
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
                    }
                    for t in tabs
                ],
            }
        )
    )


class ScenarioTabSelection(BaseModel):
    tab_id: str
    selection_rationale: str | None = None


@app.post("/scenario-sets/{scenario_set_id}/select-tab")
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


@app.post("/scenario-framing-tabs/{tab_id}/run")
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
          pp.authority_id,
          pp.metadata_jsonb->>'plan_cycle_id' AS plan_cycle_id
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
                _link_evidence_to_move(run_id=run_id, move_event_id=curation_move_id, evidence_refs=[e for e in evs if isinstance(e, str)], role=role)
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
    _link_evidence_to_move(run_id=run_id, move_event_id=interpretation_move_id, evidence_refs=interp_evidence_refs, role="supporting")
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
        uncertainty_remaining=["PolicyClause parsing is LLM-assisted and non-deterministic; verify clause boundaries and legal weight against the source plan cycle."],
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

    _db_execute(
        """
        UPDATE scenario_framing_tabs
        SET framing_id = %s, run_id = %s::uuid, status = %s, trajectory_id = %s::uuid,
            judgement_sheet_ref = %s, updated_at = %s
        WHERE id = %s::uuid
        """,
        (
            framing_obj["frame_id"],
            run_id,
            "complete" if not position_errs else "partial",
            trajectory_id,
            f"trajectory::{trajectory_id}",
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
    _link_evidence_to_move(
        run_id=run_id, move_event_id=positioning_move_id, evidence_refs=curated_evidence_refs[:50], role="supporting"
    )

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


@app.get("/scenario-framing-tabs/{tab_id}/sheet")
def get_scenario_tab_sheet(tab_id: str) -> JSONResponse:
    tab = _db_fetch_one(
        """
        SELECT id, scenario_id, political_framing_id, framing_id, run_id, status, trajectory_id
        FROM scenario_framing_tabs
        WHERE id = %s::uuid
        """,
        (tab_id,),
    )
    if not tab:
        raise HTTPException(status_code=404, detail="ScenarioFramingTab not found")

    if not tab.get("trajectory_id"):
        return JSONResponse(content=jsonable_encoder({"tab_id": tab_id, "status": tab.get("status"), "trajectory": None, "sheet": None}))

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

    return JSONResponse(content=jsonable_encoder({"tab_id": tab_id, "status": tab.get("status"), "run_id": tab.get("run_id"), "trajectory": trajectory, "sheet": traj["judgement_sheet_jsonb"] or {}}))


@app.get("/trace/runs/{run_id}")
def trace_run(run_id: str, mode: str = "summary") -> JSONResponse:
    if mode not in {"summary", "inspect", "forensic"}:
        raise HTTPException(status_code=400, detail="mode must be one of: summary, inspect, forensic")

    run = _db_fetch_one("SELECT id, profile, culp_stage_id, anchors_jsonb, created_at FROM runs WHERE id = %s::uuid", (run_id,))
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    moves = _db_fetch_all(
        """
        SELECT id, move_type, sequence, status, created_at, inputs_jsonb, outputs_jsonb,
               evidence_refs_considered_jsonb, tool_run_ids_jsonb, uncertainty_remaining_jsonb
        FROM move_events
        WHERE run_id = %s::uuid
        ORDER BY sequence ASC
        """,
        (run_id,),
    )

    audit_rows = _db_fetch_all(
        """
        SELECT id, timestamp, event_type, actor_type, actor_id, payload_jsonb
        FROM audit_events
        WHERE run_id = %s::uuid
        ORDER BY timestamp ASC
        """,
        (run_id,),
    )

    move_ids = [str(m["id"]) for m in moves]
    evidence_links: list[dict[str, Any]] = []
    if move_ids:
        evidence_links = _db_fetch_all(
            """
            SELECT
              rel.id AS link_id,
              rel.move_event_id,
              rel.role,
              er.source_type,
              er.source_id,
              er.fragment_id
            FROM reasoning_evidence_links rel
            JOIN evidence_refs er ON er.id = rel.evidence_ref_id
            WHERE rel.move_event_id = ANY(%s::uuid[])
            ORDER BY rel.created_at ASC
            """,
            (move_ids,),
        )

    def evidence_ref_str(row: dict[str, Any]) -> str:
        return f"{row['source_type']}::{row['source_id']}::{row['fragment_id']}"

    tool_run_ids: list[str] = []
    for m in moves:
        ids = m.get("tool_run_ids_jsonb") or []
        if isinstance(ids, list):
            tool_run_ids.extend([str(x) for x in ids if isinstance(x, str)])
    tool_run_ids = sorted(set(tool_run_ids))

    tool_runs: list[dict[str, Any]] = []
    if tool_run_ids:
        tool_runs = _db_fetch_all(
            """
            SELECT id, tool_name, status, started_at, ended_at, confidence_hint
            FROM tool_runs
            WHERE id = ANY(%s::uuid[])
            ORDER BY started_at ASC NULLS LAST
            """,
            (tool_run_ids,),
        )

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    run_node_id = f"run::{run_id}"
    nodes.append(
        {
            "node_id": run_node_id,
            "node_type": "run",
            "label": f"Run ({run.get('profile')})",
            "ref": {"run_id": run_id, "culp_stage_id": run.get("culp_stage_id")},
            "layout": {"x": 0, "y": 0, "group": None},
            "severity": None,
        }
    )

    move_node_ids: dict[str, str] = {}
    for idx, m in enumerate(moves, start=1):
        move_id = str(m["id"])
        node_id = f"move::{move_id}"
        move_node_ids[move_id] = node_id
        status = m.get("status")
        severity = "error" if status == "error" else "warning" if status == "partial" else "info"
        nodes.append(
            {
                "node_id": node_id,
                "node_type": "move",
                "label": f"{m.get('sequence')}. {m.get('move_type')}",
                "ref": {"move_id": move_id, "move_type": m.get("move_type"), "status": status},
                "layout": {"x": 220, "y": idx * 120, "group": None},
                "severity": severity,
            }
        )
        edges.append(
            {
                "edge_id": f"edge::{uuid4()}",
                "src_id": run_node_id,
                "dst_id": node_id,
                "edge_type": "TRIGGERS",
                "label": None,
            }
        )

    tool_node_ids: dict[str, str] = {}
    tool_by_id = {str(t["id"]): t for t in tool_runs}
    for m in moves:
        move_id = str(m["id"])
        ids = m.get("tool_run_ids_jsonb") or []
        if not isinstance(ids, list):
            continue
        for j, tr_id in enumerate([x for x in ids if isinstance(x, str)], start=1):
            tr_id_str = str(tr_id)
            if tr_id_str not in tool_node_ids:
                tr = tool_by_id.get(tr_id_str) or {"tool_name": "tool", "status": "unknown"}
                status = tr.get("status")
                severity = "error" if status == "error" else "warning" if status == "partial" else "info"
                tool_node_ids[tr_id_str] = f"tool_run::{tr_id_str}"
                nodes.append(
                    {
                        "node_id": tool_node_ids[tr_id_str],
                        "node_type": "tool_run",
                        "label": f"{tr.get('tool_name')} ({status})",
                        "ref": {"tool_run_id": tr_id_str, "tool_name": tr.get("tool_name")},
                        "layout": {"x": 520, "y": (m.get("sequence") or 0) * 120 + (j * 18), "group": move_node_ids.get(move_id)},
                        "severity": severity,
                    }
                )
            edges.append(
                {
                    "edge_id": f"edge::{uuid4()}",
                    "src_id": move_node_ids.get(move_id) or run_node_id,
                    "dst_id": tool_node_ids[tr_id_str],
                    "edge_type": "USES",
                    "label": None,
                }
            )

    evidence_node_ids: dict[str, str] = {}
    for link in evidence_links:
        move_id = str(link["move_event_id"])
        ev = evidence_ref_str(link)
        if ev not in evidence_node_ids:
            evidence_node_ids[ev] = f"evidence::{ev}"
            nodes.append(
                {
                    "node_id": evidence_node_ids[ev],
                    "node_type": "evidence",
                    "label": link.get("source_type") or "evidence",
                    "ref": {"evidence_ref": ev},
                    "layout": {"x": 840, "y": 0, "group": move_node_ids.get(move_id)},
                    "severity": None,
                }
            )
        edges.append(
            {
                "edge_id": f"edge::{uuid4()}",
                "src_id": move_node_ids.get(move_id) or run_node_id,
                "dst_id": evidence_node_ids[ev],
                "edge_type": "CITES",
                "label": link.get("role"),
            }
        )

    # Also include audit events linked to the run (selection, completion, etc.)
    for idx, a in enumerate(audit_rows[:50], start=1):
        node_id = f"audit::{a['id']}"
        nodes.append(
            {
                "node_id": node_id,
                "node_type": "audit_event",
                "label": a.get("event_type") or "audit_event",
                "ref": {"audit_event_id": str(a["id"]), "timestamp": a.get("timestamp")},
                "layout": {"x": 0, "y": 120 + idx * 26, "group": None},
                "severity": None,
            }
        )
        edges.append(
            {
                "edge_id": f"edge::{uuid4()}",
                "src_id": node_id,
                "dst_id": run_node_id,
                "edge_type": "TRIGGERS",
                "label": a.get("actor_type"),
            }
        )

    trace = {
        "trace_graph_id": str(uuid4()),
        "run_id": run_id,
        "mode": mode,
        "nodes": nodes,
        "edges": edges,
        "created_at": _utc_now_iso(),
    }
    return JSONResponse(content=jsonable_encoder(trace))


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
            rel_path = str(doc.get("file_path") or "")
            if not rel_path:
                continue
            counts["documents_seen"] += 1
            src_path = (pack_dir / rel_path).resolve()
            if not src_path.exists():
                errors.append(f"Missing file: {src_path}")
                _update_ingest_batch_progress(
                    ingest_batch_id=ingest_batch_id,
                    status="running",
                    counts=counts,
                    errors=errors,
                    document_ids=document_ids,
                    plan_cycle_id=plan_cycle_id,
                    progress={"phase": "running", "current_document": rel_path, "note": "missing_file"},
                )
                continue

            _update_ingest_batch_progress(
                ingest_batch_id=ingest_batch_id,
                status="running",
                counts=counts,
                errors=errors,
                document_ids=document_ids,
                plan_cycle_id=plan_cycle_id,
                progress={"phase": "chunking", "current_document": rel_path, "phased": phased},
            )

            object_name = f"raw/authority_packs/{authority_id}/{src_path.name}"
            content_type = mimetypes.guess_type(src_path.name)[0] or "application/octet-stream"

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
                        json.dumps(
                            {
                                "title": doc.get("title") or src_path.stem,
                                "document_type": doc.get("document_type"),
                                "source": doc.get("source") or "authority_pack",
                                "content_type": content_type,
                            },
                            ensure_ascii=False,
                        ),
                        blob_path,
                    ),
                )
                counts["documents_created"] += 1

            document_ids.append(document_id)
            docs_for_postprocessing.append(
                {
                    "document_id": document_id,
                    "document_title": doc.get("title") or src_path.stem,
                    "source_rel_path": rel_path,
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


@app.post("/ingest/authority-packs/{authority_id}/start")
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

    def _runner() -> None:
        try:
            _run_authority_pack_ingest(
                authority_id=authority_id,
                pack_dir=pack_dir,
                manifest=manifest,
                documents=documents,
                plan_cycle_row=plan_cycle_row,
                plan_cycle_id=plan_cycle_id,
                ingest_batch_id=ingest_batch_id,
                tool_run_id=tool_run_id,
                started_at=started_at,
            )
        except Exception:  # noqa: BLE001
            # Errors are persisted into ingest_batches/tool_runs; avoid crashing the API worker.
            pass

    threading.Thread(target=_runner, daemon=True).start()
    _audit_event(
        event_type="authority_pack_ingest_started",
        actor_type="system",
        payload={"authority_id": authority_id, "plan_cycle_id": plan_cycle_id, "ingest_batch_id": ingest_batch_id},
    )

    return JSONResponse(
        status_code=202,
        content=jsonable_encoder(
            {
                "authority_id": authority_id,
                "plan_cycle_id": plan_cycle_id,
                "ingest_batch_id": ingest_batch_id,
                "tool_run_id": tool_run_id,
                "status": "running",
            }
        ),
    )


@app.post("/ingest/authority-packs/{authority_id}")
def ingest_authority_pack(authority_id: str, body: AuthorityPackIngestRequest | None = None) -> JSONResponse:
    body = body or AuthorityPackIngestRequest()

    pack_dir = _authority_packs_root() / authority_id
    if not pack_dir.exists():
        raise HTTPException(status_code=404, detail=f"Authority pack not found: {authority_id}")

    manifest = _load_authority_pack_manifest(authority_id)
    documents = _normalize_authority_pack_documents(manifest)
    if not documents:
        raise HTTPException(status_code=400, detail=f"No documents listed in authority pack manifest for '{authority_id}'")

    plan_cycle_row, plan_cycle_id, ingest_batch_id, tool_run_id, started_at = _prepare_authority_pack_ingest(
        authority_id=authority_id,
        body=body,
        manifest=manifest,
        document_count=len(documents),
    )

    result = _run_authority_pack_ingest(
        authority_id=authority_id,
        pack_dir=pack_dir,
        manifest=manifest,
        documents=documents,
        plan_cycle_row=plan_cycle_row,
        plan_cycle_id=plan_cycle_id,
        ingest_batch_id=ingest_batch_id,
        tool_run_id=tool_run_id,
        started_at=started_at,
    )
    return JSONResponse(content=jsonable_encoder(result))


@app.get("/ingest/batches")
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


@app.get("/ingest/batches/{ingest_batch_id}")
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


@app.get("/search/chunks")
def search_chunks(
    q: str,
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    active_only: bool = True,
    limit: int = 12,
) -> JSONResponse:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="q must not be empty")
    limit = max(1, min(int(limit), 50))

    like = f"%{query}%"
    where: list[str] = ["c.text ILIKE %s"]
    params: list[Any] = [like]
    if authority_id:
        where.append("d.authority_id = %s")
        params.append(authority_id)
    if plan_cycle_id:
        where.append("d.plan_cycle_id = %s::uuid")
        params.append(plan_cycle_id)
    if active_only:
        where.append("d.is_active = true")

    rows = _db_fetch_all(
        f"""
        SELECT
          c.id AS chunk_id,
          c.document_id,
          c.page_number,
          LEFT(c.text, 800) AS snippet,
          er.fragment_id AS fragment_id,
          d.metadata->>'title' AS document_title,
          d.blob_path AS blob_path,
          d.plan_cycle_id AS plan_cycle_id
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        LEFT JOIN evidence_refs er ON er.source_type = 'chunk' AND er.source_id = c.id::text
        WHERE {" AND ".join(where)}
        ORDER BY c.page_number NULLS LAST
        LIMIT %s
        """,
        tuple(params + [limit]),
    )

    results = [
        {
            "chunk_id": str(r["chunk_id"]),
            "document_id": str(r["document_id"]),
            "page_number": r["page_number"],
            "evidence_ref": f"chunk::{r['chunk_id']}::{r['fragment_id'] or 'page-unknown'}",
            "document_title": r["document_title"],
            "blob_path": r["blob_path"],
            "plan_cycle_id": str(r["plan_cycle_id"]) if r.get("plan_cycle_id") else None,
            "snippet": r["snippet"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"results": results}))


class RetrieveChunksRequest(BaseModel):
    query: str
    authority_id: str | None = None
    plan_cycle_id: str | None = None
    limit: int = 12
    rrf_k: int = 60
    use_vector: bool = True
    use_fts: bool = True
    rerank: bool = True
    rerank_top_n: int = 20


@app.post("/retrieval/chunks")
def retrieve_chunks(body: RetrieveChunksRequest) -> JSONResponse:
    out = _retrieve_chunks_hybrid_sync(
        query=body.query,
        authority_id=body.authority_id,
        plan_cycle_id=body.plan_cycle_id,
        limit=body.limit,
        rrf_k=body.rrf_k,
        use_vector=bool(body.use_vector),
        use_fts=bool(body.use_fts),
        rerank=bool(body.rerank),
        rerank_top_n=body.rerank_top_n,
    )
    return JSONResponse(content=jsonable_encoder(out))


class RetrievePolicyClausesRequest(BaseModel):
    query: str
    authority_id: str | None = None
    plan_cycle_id: str | None = None
    limit: int = 12
    rrf_k: int = 60
    use_vector: bool = True
    use_fts: bool = True
    rerank: bool = True
    rerank_top_n: int = 20


@app.post("/retrieval/policy-clauses")
def retrieve_policy_clauses(body: RetrievePolicyClausesRequest) -> JSONResponse:
    out = _retrieve_policy_clauses_hybrid_sync(
        query=body.query,
        authority_id=body.authority_id,
        plan_cycle_id=body.plan_cycle_id,
        limit=body.limit,
        rrf_k=body.rrf_k,
        use_vector=bool(body.use_vector),
        use_fts=bool(body.use_fts),
        rerank=bool(body.rerank),
        rerank_top_n=body.rerank_top_n,
    )
    return JSONResponse(content=jsonable_encoder(out))

# NOTE: Legacy monolith retained for reference while the API moves to router modules + app factory.
