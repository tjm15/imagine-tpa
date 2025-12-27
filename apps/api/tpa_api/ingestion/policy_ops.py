from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from tpa_api.db import _db_execute
from tpa_api.evidence import _parse_evidence_ref
from tpa_api.policy_utils import _normalize_policy_speech_act
from tpa_api.time_utils import _utc_now
from tpa_api.ingestion.kg_ops import _ensure_kg_node, _insert_kg_edge


def _normalize_text_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned:
            out.append(cleaned)
    return out


def _merge_matrix_fields(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    merged["inputs"] = sorted(set(_normalize_text_list(primary.get("inputs")) + _normalize_text_list(secondary.get("inputs"))))
    merged["outputs"] = sorted(set(_normalize_text_list(primary.get("outputs")) + _normalize_text_list(secondary.get("outputs"))))
    for key in ("logic_type", "matrix_title", "matrix_id", "evidence_ref", "evidence_block_id", "policy_section_id", "tool_run_id"):
        if not merged.get(key) and secondary.get(key):
            merged[key] = secondary.get(key)
    sources = {s for s in (primary.get("source"), secondary.get("source")) if isinstance(s, str)}
    if len(sources) > 1:
        merged["source"] = "hybrid"
    elif sources:
        merged["source"] = sources.pop()
    merged["quality_score"] = max(float(primary.get("quality_score") or 0.0), float(secondary.get("quality_score") or 0.0))
    return merged


def _merge_scope_fields(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    merged["geography_refs"] = sorted(set(_normalize_text_list(primary.get("geography_refs")) + _normalize_text_list(secondary.get("geography_refs"))))
    merged["development_types"] = sorted(set(_normalize_text_list(primary.get("development_types")) + _normalize_text_list(secondary.get("development_types"))))
    merged["use_classes"] = sorted(set(_normalize_text_list(primary.get("use_classes")) + _normalize_text_list(secondary.get("use_classes"))))
    merged["conditions"] = sorted(set(_normalize_text_list(primary.get("conditions")) + _normalize_text_list(secondary.get("conditions"))))
    for key in ("use_class_regime", "temporal_scope", "scope_notes", "evidence_ref", "evidence_block_id", "policy_section_id", "tool_run_id"):
        if not merged.get(key) and secondary.get(key):
            merged[key] = secondary.get(key)
    sources = {s for s in (primary.get("source"), secondary.get("source")) if isinstance(s, str)}
    if len(sources) > 1:
        merged["source"] = "hybrid"
    elif sources:
        merged["source"] = sources.pop()
    merged["quality_score"] = max(float(primary.get("quality_score") or 0.0), float(secondary.get("quality_score") or 0.0))
    return merged


def _matrix_quality_score(matrix: dict[str, Any]) -> float:
    score = 0.0
    if _normalize_text_list(matrix.get("inputs")):
        score += 1.0
    if _normalize_text_list(matrix.get("outputs")):
        score += 1.0
    logic_type = matrix.get("logic_type")
    if isinstance(logic_type, str) and logic_type.strip().lower() not in {"other", "unknown"}:
        score += 0.5
    if matrix.get("evidence_ref") or matrix.get("evidence_block_id"):
        score += 1.0
    if matrix.get("policy_section_id"):
        score += 0.5
    if matrix.get("matrix_title"):
        score += 0.25
    return score


def _scope_quality_score(scope: dict[str, Any]) -> float:
    score = 0.0
    if _normalize_text_list(scope.get("geography_refs")):
        score += 1.0
    if _normalize_text_list(scope.get("development_types")):
        score += 1.0
    if _normalize_text_list(scope.get("use_classes")):
        score += 1.0
    if _normalize_text_list(scope.get("conditions")):
        score += 0.5
    if isinstance(scope.get("scope_notes"), str) and scope.get("scope_notes").strip():
        score += 0.25
    temporal_scope = scope.get("temporal_scope")
    if isinstance(temporal_scope, dict) and any(temporal_scope.get(k) for k in ("start_date", "end_date", "phasing_stage")):
        score += 0.5
    if scope.get("evidence_ref") or scope.get("evidence_block_id"):
        score += 1.0
    if scope.get("policy_section_id"):
        score += 0.5
    return score


def _matrix_fingerprint(matrix: dict[str, Any]) -> str:
    if isinstance(matrix.get("evidence_block_id"), str):
        return f"block:{matrix.get('evidence_block_id')}"
    if isinstance(matrix.get("evidence_ref"), str):
        return f"ref:{matrix.get('evidence_ref')}"
    policy_section_id = matrix.get("policy_section_id") or "none"
    inputs = ",".join(sorted(_normalize_text_list(matrix.get("inputs"))))
    outputs = ",".join(sorted(_normalize_text_list(matrix.get("outputs"))))
    logic_type = str(matrix.get("logic_type") or "")
    title = str(matrix.get("matrix_title") or "")
    return f"fields:{policy_section_id}|{inputs}|{outputs}|{logic_type}|{title}"


def _scope_fingerprint(scope: dict[str, Any]) -> str:
    if isinstance(scope.get("evidence_block_id"), str):
        return f"block:{scope.get('evidence_block_id')}"
    if isinstance(scope.get("evidence_ref"), str):
        return f"ref:{scope.get('evidence_ref')}"
    policy_section_id = scope.get("policy_section_id") or "none"
    geography = ",".join(sorted(_normalize_text_list(scope.get("geography_refs"))))
    dev = ",".join(sorted(_normalize_text_list(scope.get("development_types"))))
    use = ",".join(sorted(_normalize_text_list(scope.get("use_classes"))))
    conditions = ",".join(sorted(_normalize_text_list(scope.get("conditions"))))
    return f"fields:{policy_section_id}|{geography}|{dev}|{use}|{conditions}"


def _confidence_hint_score(value: str | None) -> float:
    if not isinstance(value, str):
        return 0.0
    lowered = value.strip().lower()
    if lowered == "high":
        return 0.9
    if lowered == "medium":
        return 0.6
    if lowered == "low":
        return 0.3
    return 0.0


def _block_id_from_section_ref(section_ref: str | None) -> str | None:
    if not isinstance(section_ref, str) or not section_ref:
        return None
    if section_ref.startswith("p"):
        idx = 1
        while idx < len(section_ref) and section_ref[idx].isdigit():
            idx += 1
        if idx < len(section_ref) and section_ref[idx] == "-":
            return section_ref[idx + 1 :] or None
    return section_ref


def _merge_policy_logic_assets(
    *,
    docparse_matrices: list[dict[str, Any]],
    llm_matrices: list[dict[str, Any]],
    docparse_scopes: list[dict[str, Any]],
    llm_scopes: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    policy_sections: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    section_by_source = {
        s.get("source_section_id"): s.get("policy_section_id")
        for s in policy_sections
        if s.get("source_section_id") and s.get("policy_section_id")
    }
    block_to_section: dict[str, str] = {}
    for section in sections:
        if not isinstance(section, dict):
            continue
        source_section_id = section.get("section_id")
        policy_section_id = section_by_source.get(source_section_id)
        if not policy_section_id:
            continue
        for block_id in section.get("block_ids") or []:
            if isinstance(block_id, str):
                block_to_section[block_id] = policy_section_id

    block_lookup = {b.get("block_id"): b for b in block_rows if b.get("block_id")}

    def _enrich_item(item: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(item)
        evidence_ref = enriched.get("evidence_ref")
        evidence_block_id = enriched.get("evidence_block_id")
        if isinstance(evidence_block_id, str) and not evidence_ref:
            block = block_lookup.get(evidence_block_id)
            if block and isinstance(block.get("evidence_ref"), str):
                enriched["evidence_ref"] = block.get("evidence_ref")
        if not evidence_block_id and isinstance(evidence_ref, str):
            parsed = _parse_evidence_ref(evidence_ref)
            if parsed:
                block_id = _block_id_from_section_ref(parsed[2])
                if block_id:
                    enriched["evidence_block_id"] = block_id
        if not enriched.get("policy_section_id") and isinstance(enriched.get("evidence_block_id"), str):
            enriched["policy_section_id"] = block_to_section.get(enriched.get("evidence_block_id"))
        return enriched

    merged_matrices: dict[str, dict[str, Any]] = {}
    for item in (docparse_matrices or []):
        if not isinstance(item, dict):
            continue
        enriched = _enrich_item(item)
        enriched["inputs"] = _normalize_text_list(enriched.get("inputs"))
        enriched["outputs"] = _normalize_text_list(enriched.get("outputs"))
        enriched["source"] = "docparse"
        enriched["quality_score"] = _matrix_quality_score(enriched)
        merged_matrices[_matrix_fingerprint(enriched)] = enriched

    for item in (llm_matrices or []):
        if not isinstance(item, dict):
            continue
        enriched = _enrich_item(item)
        enriched["inputs"] = _normalize_text_list(enriched.get("inputs"))
        enriched["outputs"] = _normalize_text_list(enriched.get("outputs"))
        enriched["source"] = "llm"
        enriched["quality_score"] = _matrix_quality_score(enriched)
        key = _matrix_fingerprint(enriched)
        if key in merged_matrices:
            merged_matrices[key] = _merge_matrix_fields(merged_matrices[key], enriched)
        else:
            merged_matrices[key] = enriched

    merged_scopes: dict[str, dict[str, Any]] = {}
    for item in (docparse_scopes or []):
        if not isinstance(item, dict):
            continue
        enriched = _enrich_item(item)
        enriched["geography_refs"] = _normalize_text_list(enriched.get("geography_refs"))
        enriched["development_types"] = _normalize_text_list(enriched.get("development_types"))
        enriched["use_classes"] = _normalize_text_list(enriched.get("use_classes"))
        enriched["conditions"] = _normalize_text_list(enriched.get("conditions"))
        enriched["source"] = "docparse"
        enriched["quality_score"] = _scope_quality_score(enriched)
        merged_scopes[_scope_fingerprint(enriched)] = enriched

    for item in (llm_scopes or []):
        if not isinstance(item, dict):
            continue
        enriched = _enrich_item(item)
        enriched["geography_refs"] = _normalize_text_list(enriched.get("geography_refs"))
        enriched["development_types"] = _normalize_text_list(enriched.get("development_types"))
        enriched["use_classes"] = _normalize_text_list(enriched.get("use_classes"))
        enriched["conditions"] = _normalize_text_list(enriched.get("conditions"))
        enriched["source"] = "llm"
        enriched["quality_score"] = _scope_quality_score(enriched)
        key = _scope_fingerprint(enriched)
        if key in merged_scopes:
            merged_scopes[key] = _merge_scope_fields(merged_scopes[key], enriched)
        else:
            merged_scopes[key] = enriched

    return list(merged_matrices.values()), list(merged_scopes.values())


def _merge_policy_headings(
    *,
    sections: list[dict[str, Any]],
    policy_headings: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not policy_headings:
        return sections
    block_lookup = {b.get("block_id"): b for b in block_rows if b.get("block_id")}
    merged = [dict(s) for s in sections if isinstance(s, dict)]

    for heading in policy_headings:
        if not isinstance(heading, dict):
            continue
        block_id = heading.get("block_id")
        if not isinstance(block_id, str):
            continue
        policy_code = heading.get("policy_code")
        policy_title = heading.get("policy_title")
        heading_score = _confidence_hint_score(heading.get("confidence_hint"))

        matched = None
        for section in merged:
            block_ids = section.get("block_ids") if isinstance(section.get("block_ids"), list) else []
            if block_id in block_ids:
                matched = section
                break
        if not matched and isinstance(policy_code, str):
            for section in merged:
                if section.get("policy_code") == policy_code:
                    matched = section
                    break

        if matched:
            existing_score = _confidence_hint_score(matched.get("confidence_hint")) or 0.5
            if heading_score >= existing_score or not matched.get("policy_code"):
                if isinstance(policy_code, str) and policy_code.strip():
                    matched["policy_code"] = policy_code.strip()
                if isinstance(policy_title, str) and policy_title.strip():
                    matched["title"] = policy_title.strip()
                if not matched.get("heading_text"):
                    block = block_lookup.get(block_id) or {}
                    matched["heading_text"] = block.get("text")
            continue

        if heading_score >= 0.6:
            block = block_lookup.get(block_id) or {}
            merged.append(
                {
                    "section_id": f"docparse:{block_id}",
                    "policy_code": policy_code.strip() if isinstance(policy_code, str) else None,
                    "title": policy_title.strip() if isinstance(policy_title, str) else None,
                    "heading_text": block.get("text"),
                    "section_path": block.get("section_path"),
                    "block_ids": [block_id],
                    "clauses": [],
                    "definitions": [],
                    "targets": [],
                    "monitoring": [],
                    "confidence_hint": heading.get("confidence_hint"),
                    "uncertainty_note": heading.get("uncertainty_note"),
                }
            )

    return merged


def _persist_policy_logic_assets(
    *,
    document_id: str,
    run_id: str | None,
    sections: list[dict[str, Any]],
    policy_sections: list[dict[str, Any]],
    standard_matrices: list[dict[str, Any]],
    scope_candidates: list[dict[str, Any]],
    evidence_ref_map: dict[str, str],
    block_rows: list[dict[str, Any]],
) -> tuple[int, int]:
    section_by_source = {
        s.get("source_section_id"): s.get("policy_section_id")
        for s in policy_sections
        if s.get("source_section_id") and s.get("policy_section_id")
    }
    block_lookup = {b.get("block_id"): b for b in block_rows if b.get("block_id")}
    block_to_section: dict[str, str] = {}
    for section in sections:
        if not isinstance(section, dict):
            continue
        source_section_id = section.get("section_id")
        policy_section_id = section_by_source.get(source_section_id)
        if not policy_section_id:
            continue
        block_ids = section.get("block_ids") if isinstance(section.get("block_ids"), list) else []
        for block_id in block_ids:
            if isinstance(block_id, str):
                block_to_section[block_id] = policy_section_id

    matrix_count = 0
    for matrix in standard_matrices or []:
        if not isinstance(matrix, dict):
            continue
        policy_section_id = matrix.get("policy_section_id")
        evidence_ref = matrix.get("evidence_ref")
        evidence_block_id = matrix.get("evidence_block_id")
        section_ref = None
        if isinstance(evidence_ref, str):
            parsed = _parse_evidence_ref(evidence_ref)
            if parsed:
                section_ref = parsed[2]
        block_id = _block_id_from_section_ref(section_ref) if section_ref else None
        if not policy_section_id and block_id:
            policy_section_id = block_to_section.get(block_id)
        if not policy_section_id and isinstance(evidence_block_id, str):
            policy_section_id = block_to_section.get(evidence_block_id)

        evidence_ref_id = None
        if isinstance(evidence_ref, str) and evidence_ref:
            evidence_ref_id = evidence_ref_map.get(section_ref) if section_ref else evidence_ref_map.get(evidence_ref)
        if not evidence_ref_id and isinstance(evidence_block_id, str):
            block = block_lookup.get(evidence_block_id)
            if block and isinstance(block.get("evidence_ref"), str):
                evidence_ref_id = evidence_ref_map.get(block.get("evidence_ref"))
        matrix_id = str(uuid4())
        matrix_jsonb = {
            "matrix_id": matrix.get("matrix_id"),
            "matrix_title": matrix.get("matrix_title") or matrix.get("title"),
            "inputs": matrix.get("inputs"),
            "outputs": matrix.get("outputs"),
            "logic_type": matrix.get("logic_type"),
            "evidence_ref": evidence_ref,
            "evidence_block_id": evidence_block_id,
            "policy_section_id": policy_section_id,
        }
        _db_execute(
            """
            INSERT INTO policy_matrices (
              id, document_id, policy_section_id, run_id, matrix_jsonb, evidence_ref_id, metadata_jsonb, created_at
            )
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s::jsonb, %s::uuid, %s::jsonb, %s)
            """,
            (
                matrix_id,
                document_id,
                policy_section_id,
                run_id,
                json.dumps(matrix_jsonb, ensure_ascii=False),
                evidence_ref_id,
                json.dumps(
                    {
                        "source": matrix.get("source"),
                        "quality_score": matrix.get("quality_score"),
                        "tool_run_id": matrix.get("tool_run_id"),
                    },
                    ensure_ascii=False,
                ),
                _utc_now(),
            ),
        )
        _ensure_kg_node(
            node_id=f"policy_matrix::{matrix_id}",
            node_type="PolicyMatrix",
            canonical_fk=matrix_id,
            props={
                "logic_type": matrix.get("logic_type"),
                "matrix_id": matrix.get("matrix_id"),
                "matrix_title": matrix.get("matrix_title") or matrix.get("title"),
            },
        )
        if policy_section_id:
            source = matrix.get("source")
            resolve_method = "llm_policy_matrix" if source in {"llm", "hybrid"} else "docparse_standard_matrix"
            edge_class = source if isinstance(source, str) else "docparse"
            _insert_kg_edge(
                src_id=f"policy_section::{policy_section_id}",
                dst_id=f"policy_matrix::{matrix_id}",
                edge_type="CONTAINS_MATRIX",
                run_id=run_id,
                edge_class=edge_class,
                resolve_method=resolve_method,
                props={},
                evidence_ref_id=evidence_ref_id,
                tool_run_id=matrix.get("tool_run_id"),
            )
        matrix_count += 1

    scope_count = 0
    for scope in scope_candidates or []:
        if not isinstance(scope, dict):
            continue
        policy_section_id = scope.get("policy_section_id")
        evidence_ref = scope.get("evidence_ref")
        evidence_block_id = scope.get("evidence_block_id")
        section_ref = None
        if isinstance(evidence_ref, str):
            parsed = _parse_evidence_ref(evidence_ref)
            if parsed:
                section_ref = parsed[2]
        block_id = _block_id_from_section_ref(section_ref) if section_ref else None
        if not policy_section_id and block_id:
            policy_section_id = block_to_section.get(block_id)
        if not policy_section_id and isinstance(evidence_block_id, str):
            policy_section_id = block_to_section.get(evidence_block_id)

        evidence_ref_id = None
        if isinstance(evidence_ref, str) and evidence_ref:
            evidence_ref_id = evidence_ref_map.get(section_ref) if section_ref else evidence_ref_map.get(evidence_ref)
        if not evidence_ref_id and isinstance(evidence_block_id, str):
            block = block_lookup.get(evidence_block_id)
            if block and isinstance(block.get("evidence_ref"), str):
                evidence_ref_id = evidence_ref_map.get(block.get("evidence_ref"))
        scope_id = str(uuid4())
        scope_jsonb = {
            "scope_id": scope.get("id"),
            "geography_refs": scope.get("geography_refs"),
            "development_types": scope.get("development_types"),
            "use_classes": scope.get("use_classes"),
            "use_class_regime": scope.get("use_class_regime"),
            "temporal_scope": scope.get("temporal_scope"),
            "conditions": scope.get("conditions"),
            "scope_notes": scope.get("scope_notes"),
            "evidence_ref": evidence_ref,
            "evidence_block_id": evidence_block_id,
            "policy_section_id": policy_section_id,
        }
        _db_execute(
            """
            INSERT INTO policy_scopes (
              id, document_id, policy_section_id, run_id, scope_jsonb, evidence_ref_id, metadata_jsonb, created_at
            )
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s::jsonb, %s::uuid, %s::jsonb, %s)
            """,
            (
                scope_id,
                document_id,
                policy_section_id,
                run_id,
                json.dumps(scope_jsonb, ensure_ascii=False),
                evidence_ref_id,
                json.dumps(
                    {
                        "source": scope.get("source"),
                        "quality_score": scope.get("quality_score"),
                        "tool_run_id": scope.get("tool_run_id"),
                    },
                    ensure_ascii=False,
                ),
                _utc_now(),
            ),
        )
        _ensure_kg_node(
            node_id=f"policy_scope::{scope_id}",
            node_type="PolicyScope",
            canonical_fk=scope_id,
            props={},
        )
        if policy_section_id:
            source = scope.get("source")
            resolve_method = "llm_scope_candidate" if source in {"llm", "hybrid"} else "docparse_scope_candidate"
            edge_class = source if isinstance(source, str) else "docparse"
            _insert_kg_edge(
                src_id=f"policy_section::{policy_section_id}",
                dst_id=f"policy_scope::{scope_id}",
                edge_type="DEFINES_SCOPE",
                run_id=run_id,
                edge_class=edge_class,
                resolve_method=resolve_method,
                props={},
                evidence_ref_id=evidence_ref_id,
                tool_run_id=scope.get("tool_run_id"),
            )
        scope_count += 1

    return matrix_count, scope_count


def _persist_policy_structure(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    sections: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    block_lookup = {b.get("block_id"): b for b in block_rows if b.get("block_id")}
    policy_sections: list[dict[str, Any]] = []
    policy_clauses: list[dict[str, Any]] = []
    definitions: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    monitoring: list[dict[str, Any]] = []

    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(uuid4())
        block_ids = section.get("block_ids") if isinstance(section.get("block_ids"), list) else []
        block_ids = [b for b in block_ids if isinstance(b, str)]
        block_texts = [block_lookup[b]["text"] for b in block_ids if b in block_lookup]
        section_text = "\n\n".join(block_texts).strip() if block_texts else str(section.get("text") or "").strip()
        if not section_text:
            continue
        page_numbers = [block_lookup[b]["page_number"] for b in block_ids if b in block_lookup]
        page_start = min(page_numbers) if page_numbers else None
        page_end = max(page_numbers) if page_numbers else None
        span_start = min([block_lookup[b]["span_start"] for b in block_ids if b in block_lookup and block_lookup[b].get("span_start") is not None], default=None)
        span_end = max([block_lookup[b]["span_end"] for b in block_ids if b in block_lookup and block_lookup[b].get("span_end") is not None], default=None)
        span_quality = "approx" if span_start is not None and span_end is not None else "none"
        evidence_ref_id = str(uuid4())

        metadata_jsonb = {
            "source_section_id": section.get("section_id"),
            "confidence_hint": section.get("confidence_hint"),
            "uncertainty_note": section.get("uncertainty_note"),
        }
        _db_execute(
            """
            INSERT INTO policy_sections (
              id, document_id, ingest_batch_id, run_id, source_artifact_id,
              policy_code, title, section_path, heading_text, text,
              page_start, page_end, span_start, span_end, span_quality,
              evidence_ref_id, metadata_jsonb
            )
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::uuid, %s::jsonb)
            """,
            (
                section_id,
                document_id,
                ingest_batch_id,
                run_id,
                source_artifact_id,
                section.get("policy_code"),
                section.get("title"),
                section.get("section_path"),
                section.get("heading_text"),
                section_text,
                page_start,
                page_end,
                span_start,
                span_end,
                span_quality,
                evidence_ref_id,
                json.dumps(metadata_jsonb, ensure_ascii=False),
            ),
        )
        _db_execute(
            "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
            (evidence_ref_id, "policy_section", section_id, section.get("policy_code") or section_id, run_id),
        )
        _ensure_kg_node(
            node_id=f"policy_section::{section_id}",
            node_type="PolicySection",
            canonical_fk=section_id,
            props={"policy_code": section.get("policy_code"), "title": section.get("title")},
        )
        policy_sections.append(
            {
                "policy_section_id": section_id,
                "source_section_id": section.get("section_id"),
                "policy_code": section.get("policy_code"),
                "title": section.get("title"),
                "section_path": section.get("section_path"),
                "text": section_text,
                "page_start": page_start,
                "page_end": page_end,
                "evidence_ref_id": evidence_ref_id,
                "block_ids": block_ids,
            }
        )

        clauses = section.get("clauses") if isinstance(section.get("clauses"), list) else []
        for clause in clauses:
            if not isinstance(clause, dict):
                continue
            clause_text = str(clause.get("text") or "").strip()
            clause_block_ids = clause.get("block_ids") if isinstance(clause.get("block_ids"), list) else []
            clause_block_ids = [b for b in clause_block_ids if isinstance(b, str)]
            if not clause_text and clause_block_ids:
                clause_text = "\n".join([block_lookup[b]["text"] for b in clause_block_ids if b in block_lookup]).strip()
            if not clause_text:
                continue
            clause_id = str(uuid4())
            clause_pages = [block_lookup[b]["page_number"] for b in clause_block_ids if b in block_lookup]
            clause_page = clause_pages[0] if clause_pages else None
            clause_span_start = min([block_lookup[b]["span_start"] for b in clause_block_ids if b in block_lookup and block_lookup[b].get("span_start") is not None], default=None)
            clause_span_end = max([block_lookup[b]["span_end"] for b in clause_block_ids if b in block_lookup and block_lookup[b].get("span_end") is not None], default=None)
            clause_span_quality = "approx" if clause_span_start is not None and clause_span_end is not None else "none"
            speech_act = _normalize_policy_speech_act(clause.get("speech_act"), tool_run_id=None, method="llm_policy_structure_v1")
            clause_evidence_ref_id = str(uuid4())
            _db_execute(
                """
                INSERT INTO policy_clauses (
                  id, policy_section_id, run_id, clause_ref, text, page_number,
                  span_start, span_end, span_quality, speech_act_jsonb, conditions_jsonb,
                  subject, object, evidence_ref_id, source_artifact_id, metadata_jsonb
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s::uuid, %s::uuid, %s::jsonb)
                """,
                (
                    clause_id,
                    section_id,
                    run_id,
                    clause.get("clause_ref"),
                    clause_text,
                    clause_page,
                    clause_span_start,
                    clause_span_end,
                    clause_span_quality,
                    json.dumps(speech_act, ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    clause.get("subject"),
                    clause.get("object"),
                    clause_evidence_ref_id,
                    source_artifact_id,
                    json.dumps({"block_ids": clause_block_ids}, ensure_ascii=False),
                ),
            )
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (clause_evidence_ref_id, "policy_clause", clause_id, clause.get("clause_ref") or clause_id, run_id),
            )
            clause_evidence_ref = f"policy_clause::{clause_id}::{clause.get('clause_ref') or clause_id}"
            _ensure_kg_node(
                node_id=f"policy_clause::{clause_id}",
                node_type="PolicyClause",
                canonical_fk=clause_id,
                props={"policy_section_id": section_id, "clause_ref": clause.get("clause_ref")},
            )
            policy_clauses.append(
                {
                    "policy_clause_id": clause_id,
                    "policy_section_id": section_id,
                    "policy_code": section.get("policy_code"),
                    "text": clause_text,
                    "evidence_ref_id": clause_evidence_ref_id,
                    "evidence_ref": clause_evidence_ref,
                    "block_ids": clause_block_ids,
                }
            )

        for definition in section.get("definitions") if isinstance(section.get("definitions"), list) else []:
            if not isinstance(definition, dict):
                continue
            term = definition.get("term")
            definition_text = definition.get("definition_text")
            if not isinstance(term, str) or not isinstance(definition_text, str):
                continue
            definition_id = str(uuid4())
            def_evidence_ref_id = str(uuid4())
            _db_execute(
                """
                INSERT INTO policy_definitions (
                  id, policy_section_id, run_id, term, definition_text, evidence_ref_id, source_artifact_id, metadata_jsonb
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s::uuid, %s::uuid, %s::jsonb)
                """,
                (
                    definition_id,
                    section_id,
                    run_id,
                    term,
                    definition_text,
                    def_evidence_ref_id,
                    source_artifact_id,
                    json.dumps({}, ensure_ascii=False),
                ),
            )
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (def_evidence_ref_id, "policy_definition", definition_id, term, run_id),
            )
            definitions.append(
                {
                    "definition_id": definition_id,
                    "policy_section_id": section_id,
                    "term": term,
                    "evidence_ref_id": def_evidence_ref_id,
                }
            )

        for target in section.get("targets") if isinstance(section.get("targets"), list) else []:
            if not isinstance(target, dict):
                continue
            target_id = str(uuid4())
            target_evidence_ref_id = str(uuid4())
            _db_execute(
                """
                INSERT INTO policy_targets (
                  id, policy_section_id, run_id, metric, value, unit, timeframe, geography_ref, raw_text,
                  evidence_ref_id, source_artifact_id, metadata_jsonb
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s::uuid, %s::uuid, %s::jsonb)
                """,
                (
                    target_id,
                    section_id,
                    run_id,
                    target.get("metric"),
                    target.get("value"),
                    target.get("unit"),
                    target.get("timeframe"),
                    target.get("geography_ref"),
                    target.get("raw_text"),
                    target_evidence_ref_id,
                    source_artifact_id,
                    json.dumps({}, ensure_ascii=False),
                ),
            )
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (target_evidence_ref_id, "policy_target", target_id, "target", run_id),
            )
            targets.append(
                {
                    "target_id": target_id,
                    "policy_section_id": section_id,
                    "evidence_ref_id": target_evidence_ref_id,
                }
            )

        for hook in section.get("monitoring") if isinstance(section.get("monitoring"), list) else []:
            if not isinstance(hook, dict):
                continue
            indicator = hook.get("indicator_text")
            if not isinstance(indicator, str) or not indicator.strip():
                continue
            hook_id = str(uuid4())
            hook_evidence_ref_id = str(uuid4())
            _db_execute(
                """
                INSERT INTO policy_monitoring_hooks (
                  id, policy_section_id, run_id, indicator_text, evidence_ref_id, source_artifact_id, metadata_jsonb
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s::uuid, %s::uuid, %s::jsonb)
                """,
                (
                    hook_id,
                    section_id,
                    run_id,
                    indicator,
                    hook_evidence_ref_id,
                    source_artifact_id,
                    json.dumps({}, ensure_ascii=False),
                ),
            )
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (hook_evidence_ref_id, "policy_monitoring_hook", hook_id, "monitoring", run_id),
            )
            monitoring.append(
                {
                    "monitoring_hook_id": hook_id,
                    "policy_section_id": section_id,
                    "indicator_text": indicator,
                    "evidence_ref_id": hook_evidence_ref_id,
                }
            )

    return policy_sections, policy_clauses, definitions, targets, monitoring


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:80] or "mention"


def _find_trigger_spans(text: str, fragment: str) -> list[dict[str, Any]]:
    if not text or not fragment:
        return []
    spans: list[dict[str, Any]] = []
    idx = text.find(fragment)
    if idx >= 0:
        spans.append({"start": idx, "end": idx + len(fragment), "quality": "exact"})
    if spans:
        return spans
    lowered = text.lower()
    frag_lower = fragment.lower()
    start = 0
    while True:
        idx = lowered.find(frag_lower, start)
        if idx < 0:
            break
        spans.append({"start": idx, "end": idx + len(fragment), "quality": "approx"})
        start = idx + len(fragment)
    return spans


def _persist_policy_edges(
    *,
    policy_sections: list[dict[str, Any]],
    policy_clauses: list[dict[str, Any]],
    definitions: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    monitoring: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    mentions: list[dict[str, Any]],
    conditions: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
    tool_run_ids: list[str],
    run_id: str | None,
) -> None:
    section_by_code = {
        s.get("policy_code"): s.get("policy_section_id")
        for s in policy_sections
        if s.get("policy_code") and s.get("policy_section_id")
    }
    clause_ref_map = {c.get("policy_clause_id"): c for c in policy_clauses if c.get("policy_clause_id")}
    block_lookup = {b.get("block_id"): b for b in block_rows if b.get("block_id")}
    tool_run_id = tool_run_ids[0] if tool_run_ids else None

    for definition in definitions:
        definition_id = definition.get("definition_id")
        section_id = definition.get("policy_section_id")
        if not definition_id or not section_id:
            continue
        _insert_kg_edge(
            src_id=f"policy_section::{section_id}",
            dst_id=f"definition::{definition_id}",
            edge_type="DEFINES",
            run_id=run_id,
            edge_class="llm",
            resolve_method="llm_policy_structure_v1",
            props={"term": definition.get("term")},
            evidence_ref_id=definition.get("evidence_ref_id"),
            tool_run_id=tool_run_id,
        )

    for target in targets:
        target_id = target.get("target_id")
        section_id = target.get("policy_section_id")
        if not target_id or not section_id:
            continue
        _insert_kg_edge(
            src_id=f"policy_section::{section_id}",
            dst_id=f"target::{target_id}",
            edge_type="TARGET_OF",
            run_id=run_id,
            edge_class="llm",
            resolve_method="llm_policy_structure_v1",
            props={},
            evidence_ref_id=target.get("evidence_ref_id"),
            tool_run_id=tool_run_id,
        )

    for hook in monitoring:
        hook_id = hook.get("monitoring_hook_id")
        section_id = hook.get("policy_section_id")
        if not hook_id or not section_id:
            continue
        _insert_kg_edge(
            src_id=f"policy_section::{section_id}",
            dst_id=f"monitoring::{hook_id}",
            edge_type="MONITORS",
            run_id=run_id,
            edge_class="llm",
            resolve_method="llm_policy_structure_v1",
            props={},
            evidence_ref_id=hook.get("evidence_ref_id"),
            tool_run_id=tool_run_id,
        )

    for cite in citations:
        source_clause_id = cite.get("source_clause_id")
        target_code = cite.get("target_policy_code")
        if not source_clause_id or not target_code:
            continue
        src = clause_ref_map.get(source_clause_id)
        dst_section_id = section_by_code.get(target_code)
        if dst_section_id:
            dst_id = f"policy_section::{dst_section_id}"
        else:
            dst_id = f"policy_ref::{_slugify(str(target_code))}"
            _ensure_kg_node(node_id=dst_id, node_type="PolicyRef", canonical_fk=None, props={"policy_code": target_code})
        _insert_kg_edge(
            src_id=f"policy_clause::{source_clause_id}",
            dst_id=dst_id,
            edge_type="CITES",
            run_id=run_id,
            edge_class="llm",
            resolve_method="llm_policy_edge_parse_v1",
            props={"confidence": cite.get("confidence")},
            evidence_ref_id=src.get("evidence_ref_id") if src else None,
            tool_run_id=tool_run_id,
        )

    if mentions:
        _persist_policy_clause_mentions(
            mentions=mentions,
            clause_ref_map=clause_ref_map,
            tool_run_id=tool_run_id,
            run_id=run_id,
        )

    if conditions:
        _apply_clause_conditions(
            conditions=conditions,
            clause_ref_map=clause_ref_map,
            block_lookup=block_lookup,
            run_id=run_id,
        )


def _persist_policy_clause_mentions(
    *,
    mentions: list[dict[str, Any]],
    clause_ref_map: dict[str, dict[str, Any]],
    tool_run_id: str | None,
    run_id: str | None,
) -> None:
    for mention in mentions:
        source_clause_id = mention.get("source_clause_id")
        mention_text = mention.get("mention_text")
        mention_kind = mention.get("mention_kind")
        if not source_clause_id or not mention_text or not mention_kind:
            continue
        clause = clause_ref_map.get(source_clause_id)
        evidence_ref_id = clause.get("evidence_ref_id") if clause else None
        _db_execute(
            """
            INSERT INTO policy_clause_mentions (
              id, policy_clause_id, run_id, mention_text, mention_kind, evidence_refs_jsonb,
              resolved_entity_type, resolved_entity_id, resolution_confidence, tool_run_id, metadata_jsonb, created_at
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s, %s, %s, %s::uuid, %s::jsonb, %s)
            """,
            (
                str(uuid4()),
                source_clause_id,
                run_id,
                mention_text,
                mention_kind,
                json.dumps([evidence_ref_id] if evidence_ref_id else [], ensure_ascii=False),
                None,
                None,
                None,
                tool_run_id,
                json.dumps({"confidence": mention.get("confidence")}, ensure_ascii=False),
                _utc_now(),
            ),
        )


def _apply_clause_conditions(
    *,
    conditions: list[dict[str, Any]],
    clause_ref_map: dict[str, dict[str, Any]],
    block_lookup: dict[str, dict[str, Any]],
    run_id: str | None,
) -> None:
    by_clause: dict[str, list[dict[str, Any]]] = {}
    allowed_ops = {"EXCEPTION", "QUALIFICATION", "DEPENDENCY", "DISCRETION_GATE", "PRIORITY_OVERRIDE"}
    allowed_severity = {"hard", "soft", "discretionary"}
    allowed_test_type = {"binary", "graded", "narrative"}
    for cond in conditions:
        source_clause_id = cond.get("source_clause_id")
        trigger_text = cond.get("trigger_text")
        operator = cond.get("operator")
        if not source_clause_id or not trigger_text or not operator:
            continue
        if operator not in allowed_ops:
            continue
        clause = clause_ref_map.get(source_clause_id)
        evidence_ref = clause.get("evidence_ref") if clause else None
        clause_block_ids = clause.get("block_ids") if isinstance(clause.get("block_ids"), list) else []
        clause_block_ids = [b for b in clause_block_ids if isinstance(b, str)]
        span_refs: list[str] = []
        trigger_spans: list[dict[str, Any]] = []
        for block_id in clause_block_ids:
            block = block_lookup.get(block_id)
            if not block:
                continue
            block_text = str(block.get("text") or "")
            spans = _find_trigger_spans(block_text, str(trigger_text))
            if not spans:
                continue
            block_evidence_ref = block.get("evidence_ref")
            if block_evidence_ref and isinstance(block_evidence_ref, str):
                span_refs.append(block_evidence_ref)
            for span in spans:
                trigger_spans.append(
                    {
                        "block_id": block_id,
                        "span_start": span.get("start"),
                        "span_end": span.get("end"),
                        "span_quality": span.get("quality"),
                        "evidence_ref": block_evidence_ref,
                    }
                )
        if not span_refs and evidence_ref and isinstance(evidence_ref, str):
            span_refs = [evidence_ref]
        cond_key = f"{source_clause_id}|{operator}|{trigger_text}"
        condition_id = hashlib.sha1(cond_key.encode("utf-8")).hexdigest()
        item = {
            "condition_id": condition_id,
            "operator": operator,
            "trigger_text": trigger_text,
            "testable": bool(cond.get("testable")),
            "requires": cond.get("requires") if isinstance(cond.get("requires"), list) else [],
            "severity": cond.get("severity") if cond.get("severity") in allowed_severity else None,
            "test_type": cond.get("test_type") if cond.get("test_type") in allowed_test_type else None,
            "span_evidence_refs": span_refs,
            "trigger_spans": trigger_spans,
        }
        by_clause.setdefault(source_clause_id, []).append(item)

    for clause_id, items in by_clause.items():
        _db_execute(
            """
            UPDATE policy_clauses
            SET conditions_jsonb = %s::jsonb
            WHERE id = %s::uuid
            """,
            (json.dumps(items, ensure_ascii=False), clause_id),
        )
