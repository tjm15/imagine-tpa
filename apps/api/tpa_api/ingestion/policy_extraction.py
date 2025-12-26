from __future__ import annotations

import json
from uuid import uuid4
from typing import Any

from tpa_api.db import _db_execute
from tpa_api.time_utils import _utc_now
from tpa_api.providers.factory import get_llm_provider
from tpa_api.services.prompts import PromptService


def _slice_blocks_for_llm(
    blocks: list[dict[str, Any]],
    *,
    max_chars: int = 12000,
    max_blocks: int = 140,
) -> list[list[dict[str, Any]]]:
    """
    Slices blocks into chunks suitable for LLM context windows.
    Simple heuristic implementation.
    """
    slices: list[list[dict[str, Any]]] = []
    current_slice: list[dict[str, Any]] = []
    current_chars = 0
    
    for block in blocks:
        text = block.get("text") or ""
        chars = len(text)
        
        # If adding this block exceeds limits, push current slice and start new one
        if current_slice and (len(current_slice) >= max_blocks or current_chars + chars > max_chars):
            slices.append(current_slice)
            current_slice = []
            current_chars = 0
            
        current_slice.append(block)
        current_chars += chars
        
    if current_slice:
        slices.append(current_slice)
        
    return slices


def run_llm_prompt(
    prompt_id: str,
    prompt_version: int,
    prompt_name: str,
    purpose: str,
    system_template: str,
    user_payload: dict[str, Any],
    output_schema: str | None = None,
    run_id: str | None = None,
    ingest_batch_id: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """
    Helper to run LLM via Provider + PromptService.
    """
    prompt_svc = PromptService()
    # Register the prompt (ensure DB knows about it)
    prompt_svc.register_prompt(
        prompt_id=prompt_id,
        version=prompt_version,
        name=prompt_name,
        purpose=purpose,
        template=system_template,
        output_schema={"ref": output_schema} if output_schema else None
    )
    
    provider = get_llm_provider()
    
    messages = [
        {"role": "system", "content": system_template},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
    ]
    
    try:
        result = provider.generate_structured(
            messages=messages,
            options={
                "run_id": run_id,
                "ingest_batch_id": ingest_batch_id,
                "temperature": 0.0 # Deterministic-ish for extraction
            }
        )
        return result.get("json"), None, [] # tool_run_id is inside provider logs, we might need to fetch it if we want to link explicitly here?
        # Provider logs ToolRun. The result dict doesn't strictly return tool_run_id based on my interface.
        # I should probably update the interface to return metadata including tool_run_id?
        # For now, I'll rely on the provider logging.
    except Exception as e:
        return None, None, [str(e)]


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


def _build_sections_from_headings(
    *,
    policy_headings: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not policy_headings or not block_rows:
        return []
    block_order = [b for b in block_rows if b.get("block_id")]
    index_by_id = {b["block_id"]: idx for idx, b in enumerate(block_order)}
    block_ids_in_order = [b["block_id"] for b in block_order]
    block_lookup = {b.get("block_id"): b for b in block_order if b.get("block_id")}

    headings = [
        h
        for h in policy_headings
        if isinstance(h, dict) and isinstance(h.get("block_id"), str) and h.get("block_id") in index_by_id
    ]
    headings = sorted(headings, key=lambda h: index_by_id[h["block_id"]])
    if not headings:
        return []

    sections: list[dict[str, Any]] = []
    for idx, heading in enumerate(headings):
        heading_block_id = heading.get("block_id")
        if not isinstance(heading_block_id, str):
            continue
        start_idx = index_by_id[heading_block_id]
        end_idx = index_by_id[headings[idx + 1]["block_id"]] if idx + 1 < len(headings) else len(block_ids_in_order)
        section_block_ids = block_ids_in_order[start_idx:end_idx]
        heading_block = block_lookup.get(heading_block_id) or {}
        sections.append(
            {
                "section_id": f"docparse:{heading_block_id}",
                "policy_code": heading.get("policy_code"),
                "title": heading.get("policy_title"),
                "heading_text": heading_block.get("text"),
                "section_path": heading_block.get("section_path"),
                "block_ids": section_block_ids,
                "clauses": [],
                "definitions": [],
                "targets": [],
                "monitoring": [],
                "confidence_hint": heading.get("confidence_hint"),
                "uncertainty_note": heading.get("uncertainty_note"),
            }
        )
    return sections


def extract_policy_structure(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    document_id: str,
    document_title: str,
    blocks: list[dict[str, Any]],
    policy_headings: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """
    Extracts policy sections and clauses using LLM.
    Returns (sections, tool_run_ids, errors).
    """
    if not blocks:
        return [], [], ["no_blocks"]

    # 1. Heading-based splitting (Fast Path)
    if policy_headings:
        sections = _build_sections_from_headings(policy_headings=policy_headings, block_rows=blocks)
        if sections:
            prompt_id = "policy_clause_split_v1"
            system_template = (
                "You are a planning policy clause splitter. Return ONLY JSON with the following shape:\n"
                "{\n"
                '  "clauses": [\n'
                "    {\n"
                '      "clause_id": "string",\n'
                '      "clause_ref": "string|null",\n'
                '      "text": "string",\n'
                '      "block_ids": ["block_id", "..."],\n'
                '      "speech_act": {"normative_force": "...", "strength_hint": "...", "ambiguity_flags": [], "key_terms": [], "officer_interpretation_space": "...", "limitations_text": "..."},\n'
                '      "subject": "string|null",\n'
                '      "object": "string|null"\n'
                "    }\n"
                "  ],\n"
                '  "definitions": [\n'
                '    {"term": "string", "definition_text": "string", "block_ids": ["block_id", "..."]}\n'
                "  ],\n"
                '  "targets": [\n'
                '    {"metric": "string|null", "value": "number|null", "unit": "string|null", "timeframe": "string|null", "geography_ref": "string|null", "raw_text": "string", "block_ids": ["block_id", "..."]}\n'
                "  ],\n"
                '  "monitoring": [\n'
                '    {"indicator_text": "string", "block_ids": ["block_id", "..."]}\n'
                "  ],\n"
                '  "deliberate_omissions": [],\n'
                '  "limitations": []\n'
                "}\n"
                "Rules:\n"
                "- Use ONLY provided block_ids for evidence.\n"
                "- Do not invent clauses without block_ids.\n"
                "- If unsure, return empty lists and use unknown speech_act values.\n"
            )

            block_lookup = {b.get("block_id"): b for b in blocks if b.get("block_id")}
            tool_run_ids: list[str] = []
            errors: list[str] = []
            
            for section in sections:
                block_ids = section.get("block_ids") if isinstance(section.get("block_ids"), list) else []
                section_blocks = [
                    {
                        "block_id": block_id,
                        "type": block_lookup.get(block_id, {}).get("type"),
                        "text": block_lookup.get(block_id, {}).get("text"),
                        "page_number": block_lookup.get(block_id, {}).get("page_number"),
                        "section_path": block_lookup.get(block_id, {}).get("section_path"),
                    }
                    for block_id in block_ids
                    if block_lookup.get(block_id) and block_lookup.get(block_id).get("text")
                ]
                
                payload = {
                    "document_id": document_id,
                    "document_title": document_title,
                    "policy_section": {
                        "section_id": section.get("section_id"),
                        "policy_code": section.get("policy_code"),
                        "title": section.get("title"),
                        "heading_text": section.get("heading_text"),
                        "section_path": section.get("section_path"),
                    },
                    "blocks": section_blocks,
                }
                
                # Use helper to run LLM
                json_result, tool_run_id, errs = run_llm_prompt(
                    prompt_id=prompt_id,
                    prompt_version=1,
                    prompt_name="Policy clause splitter",
                    purpose="Split policy section text into clauses and extract definitions, targets, and monitoring hooks.",
                    system_template=system_template,
                    user_payload=payload,
                    output_schema="schemas/PolicySectionClauseParseResult.schema.json",
                    run_id=run_id,
                    ingest_batch_id=ingest_batch_id
                )
                
                if tool_run_id:
                    tool_run_ids.append(tool_run_id)
                errors.extend(errs)
                
                if isinstance(json_result, dict):
                    for key in ("clauses", "definitions", "targets", "monitoring"):
                        items = json_result.get(key)
                        if isinstance(items, list):
                            section[key] = [item for item in items if isinstance(item, dict)]
                            
            return sections, tool_run_ids, errors

    # 2. Block-slicing fallback (Slow Path)
    prompt_id = "policy_structure_parse_v1"
    system_template = (
        "You are a planning policy parser. Return ONLY JSON with the following shape:\n"
        "{\n"
        '  "policy_sections": [\n'
        "    {\n"
        '      "section_id": "string",\n'
        '      "policy_code": "string|null",\n'
        '      "title": "string|null",\n'
        '      "heading_text": "string|null",\n'
        '      "section_path": "string|null",\n'
        '      "block_ids": ["block_id", "..."],\n'
        '      "clauses": [\n'
        "        {\n"
        '          "clause_id": "string",\n'
        '          "clause_ref": "string|null",\n'
        '          "text": "string",\n'
        '          "block_ids": ["block_id", "..."],\n'
        '          "speech_act": {"normative_force": "...", "strength_hint": "...", "ambiguity_flags": [], "key_terms": [], "officer_interpretation_space": "...", "limitations_text": "..."},\n'
        '          "subject": "string|null",\n'
        '          "object": "string|null"\n'
        "        }\n"
        "      ],\n"
        '      "definitions": [\n'
        '        {"term": "string", "definition_text": "string", "block_ids": ["block_id", "..."]}\n'
        "      ],\n"
        '      "targets": [\n'
        '        {"metric": "string|null", "value": "number|null", "unit": "string|null", "timeframe": "string|null", "geography_ref": "string|null", "raw_text": "string", "block_ids": ["block_id", "..."]}\n'
        "      ],\n"
        '      "monitoring": [\n'
        '        {"indicator_text": "string", "block_ids": ["block_id", "..."]}\n'
        "      ]\n"
        "    }\n"
        "  ],\n"
        '  "deliberate_omissions": [],\n'
        '  "limitations": []\n'
        "}\n"
        "Rules:\n"
        "- Use ONLY provided block_ids for evidence.\n"
        "- Do not invent clauses without block_ids.\n"
        "- If unsure, return empty lists and use unknown speech_act values.\n"
    )

    slices = _slice_blocks_for_llm(blocks)
    merged: dict[str, dict[str, Any]] = {}
    tool_run_ids: list[str] = []
    errors: list[str] = []

    for slice_blocks in slices:
        payload = {
            "document_id": document_id,
            "document_title": document_title,
            "blocks": [
                {
                    "block_id": b.get("block_id"),
                    "type": b.get("type"),
                    "text": b.get("text"),
                    "page_number": b.get("page_number"),
                    "section_path": b.get("section_path"),
                }
                for b in slice_blocks
                if b.get("block_id") and b.get("text")
            ],
        }
        
        json_result, tool_run_id, errs = run_llm_prompt(
            prompt_id=prompt_id,
            prompt_version=1,
            prompt_name="Policy structure parser",
            purpose="Extract policy sections, clauses, definitions, targets, and monitoring hooks from layout blocks.",
            system_template=system_template,
            user_payload=payload,
            output_schema="schemas/PolicyStructureParseResult.schema.json",
            run_id=run_id,
            ingest_batch_id=ingest_batch_id
        )
        
        if tool_run_id:
            tool_run_ids.append(tool_run_id)
        errors.extend(errs)
        
        if isinstance(json_result, dict):
            sections_list = json_result.get("policy_sections")
            if isinstance(sections_list, list):
                for section in sections_list:
                    if not isinstance(section, dict):
                        continue
                    block_ids = section.get("block_ids") if isinstance(section.get("block_ids"), list) else []
                    block_ids = [b for b in block_ids if isinstance(b, str)]
                    key = section.get("policy_code") or section.get("heading_text") or (block_ids[0] if block_ids else None)
                    if not key:
                        key = str(uuid4())
                    
                    existing = merged.get(str(key))
                    if not existing:
                        merged[str(key)] = {**section, "block_ids": block_ids}
                        continue
                        
                    existing_blocks = existing.get("block_ids") if isinstance(existing.get("block_ids"), list) else []
                    existing["block_ids"] = sorted(set(existing_blocks + block_ids))
                    
                    for list_key in ("clauses", "definitions", "targets", "monitoring"):
                        incoming = section.get(list_key) if isinstance(section.get(list_key), list) else []
                        if not incoming:
                            continue
                        current = existing.get(list_key) if isinstance(existing.get(list_key), list) else []
                        current.extend([item for item in incoming if isinstance(item, dict)])
                        existing[list_key] = current

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


def extract_policy_logic_assets(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    document_id: str,
    document_title: str,
    policy_sections: list[dict[str, Any]],
    block_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """
    Extracts policy matrices and scope candidates.
    Returns (matrices, scopes, errors).
    """
    if not policy_sections:
        return [], [], []

    block_lookup = {b.get("block_id"): b for b in block_rows if b.get("block_id")}
    errors: list[str] = []
    matrices: list[dict[str, Any]] = []
    scopes: list[dict[str, Any]] = []

    system_template = (
        "You are a planning policy logic extractor. Return ONLY valid JSON with:\n"
        "{\n"
        '  "standard_matrices": [\n'
        '    {"matrix_id": "string|null", "matrix_title": "string|null", "inputs": ["..."], "outputs": ["..."], '
        '     "logic_type": "Lookup|Multiplication|Threshold|Other", "evidence_block_id": "block_id|null"}\n'
        "  ],\n"
        '  "scope_candidates": [\n'
        '    {\n'
        '      "id": "string|null",\n'
        '      "geography_refs": ["..."],\n'
        '      "development_types": ["..."],\n'
        '      "use_classes": ["..."],\n'
        '      "use_class_regime": "2020_Amendment|Pre_2020|Sui_Generis|unknown",\n'
        '      "temporal_scope": {"start_date": null, "end_date": null, "phasing_stage": null},\n'
        '      "conditions": ["..."],\n'
        '      "scope_notes": "string|null",\n'
        '      "evidence_block_id": "block_id|null"\n'
        "    }\n"
        "  ],\n"
        '  "limitations": []\n'
        "}\n"
        "Rules:\n"
        "- Use ONLY provided block_id values for evidence_block_id.\n"
        "- If unsure, return empty lists.\n"
    )

    for section in policy_sections:
        section_id = section.get("policy_section_id")
        block_ids = section.get("block_ids") if isinstance(section.get("block_ids"), list) else []
        section_blocks = [
            {
                "block_id": block_id,
                "text": block_lookup.get(block_id, {}).get("text"),
                "page_number": block_lookup.get(block_id, {}).get("page_number"),
            }
            for block_id in block_ids
            if block_lookup.get(block_id) and block_lookup.get(block_id).get("text")
        ]
        if not section_blocks:
            continue
            
        payload = {
            "document_id": document_id,
            "document_title": document_title,
            "policy_section": {
                "policy_section_id": section_id,
                "policy_code": section.get("policy_code"),
                "title": section.get("title"),
                "section_path": section.get("section_path"),
            },
            "blocks": section_blocks,
        }
        
        json_result, tool_run_id, errs = run_llm_prompt(
            prompt_id="policy_logic_assets_v1",
            prompt_version=1,
            prompt_name="Policy logic assets extractor",
            purpose="Extract matrices and scope candidates from policy sections.",
            system_template=system_template,
            user_payload=payload,
            output_schema=None,
            run_id=run_id,
            ingest_batch_id=ingest_batch_id
        )
        
        if errs:
            errors.extend(errs)
            
        if isinstance(json_result, dict):
            for matrix in json_result.get("standard_matrices") or []:
                if not isinstance(matrix, dict):
                    continue
                evidence_block_id = matrix.get("evidence_block_id")
                if isinstance(evidence_block_id, str) and not matrix.get("evidence_ref"):
                    block = block_lookup.get(evidence_block_id)
                    if block and isinstance(block.get("evidence_ref"), str):
                        matrix["evidence_ref"] = block.get("evidence_ref")
                matrix["inputs"] = _normalize_text_list(matrix.get("inputs"))
                matrix["outputs"] = _normalize_text_list(matrix.get("outputs"))
                matrix["policy_section_id"] = section_id
                matrix["tool_run_id"] = tool_run_id
                matrices.append(matrix)
                
            for scope in json_result.get("scope_candidates") or []:
                if not isinstance(scope, dict):
                    continue
                evidence_block_id = scope.get("evidence_block_id")
                if isinstance(evidence_block_id, str) and not scope.get("evidence_ref"):
                    block = block_lookup.get(evidence_block_id)
                    if block and isinstance(block.get("evidence_ref"), str):
                        scope["evidence_ref"] = block.get("evidence_ref")
                scope["geography_refs"] = _normalize_text_list(scope.get("geography_refs"))
                scope["development_types"] = _normalize_text_list(scope.get("development_types"))
                scope["use_classes"] = _normalize_text_list(scope.get("use_classes"))
                scope["conditions"] = _normalize_text_list(scope.get("conditions"))
                scope["policy_section_id"] = section_id
                scope["tool_run_id"] = tool_run_id
                scopes.append(scope)

def _slugify(text: str) -> str:
    cleaned = "".join(c.lower() if c.isalnum() or c in ("-", "_") else "-" for c in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:80] or "mention"


def extract_edges(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    policy_clauses: list[dict[str, Any]],
    policy_codes: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    """
    Extracts policy citations, clause mentions, and clause conditions using LLM.
    Returns (citations, mentions, conditions, tool_run_ids, errors).
    """
    if not policy_clauses:
        return [], [], [], [], ["no_clauses"]
    
    prompt_id = "policy_edge_parse_v1"
    system_template = (
        "You are extracting citations and mentions from planning policy clauses.\n"
        "Return ONLY JSON with shape:\n"
        "{\n"
        '  "citations": [\n'
        '    {"source_clause_id": "uuid", "target_policy_code": "string", "confidence": "low|medium|high"}\n'
        "  ],\n"
        '  "mentions": [\n'
        '    {"source_clause_id": "uuid", "mention_text": "string", "mention_kind": "place|constraint|designation|policy_ref|defined_term|metric|other", "confidence": "low|medium|high"}\n'
        "  ],\n"
        '  "conditions": [\n'
        '    {"source_clause_id": "uuid", "trigger_text": "string", "operator": "EXCEPTION|QUALIFICATION|DEPENDENCY|DISCRETION_GATE|PRIORITY_OVERRIDE", "testable": true, "requires": [], "severity": "hard|soft|discretionary", "test_type": "binary|graded|narrative", "confidence": "low|medium|high"}\n'
        "  ]\n"
        "}\n"
        "Rules:\n"
        "- Only cite policy codes that appear in the provided policy_codes list.\n"
        "- Use mention_kind based on context; do not invent entities.\n"
        "- Conditions must quote the trigger text (unless/subject to/where appropriate).\n"
    )

    tool_run_ids: list[str] = []
    errors: list[str] = []
    citations: list[dict[str, Any]] = []
    mentions: list[dict[str, Any]] = []
    conditions: list[dict[str, Any]] = []

    batch_size = 30
    for i in range(0, len(policy_clauses), batch_size):
        batch = policy_clauses[i : i + batch_size]
        payload = {
            "policy_codes": policy_codes,
            "clauses": [{"policy_clause_id": c.get("policy_clause_id"), "text": c.get("text")} for c in batch],
        }
        
        json_result, tool_run_id, errs = run_llm_prompt(
            prompt_id=prompt_id,
            prompt_version=1,
            prompt_name="Policy edge parser",
            purpose="Extract policy citations, clause mentions, and clause conditions from clauses.",
            system_template=system_template,
            user_payload=payload,
            output_schema="schemas/PolicyEdgeParseResult.schema.json",
            run_id=run_id,
            ingest_batch_id=ingest_batch_id
        )
        
        if tool_run_id:
            tool_run_ids.append(tool_run_id)
        errors.extend(errs)
        
        if isinstance(json_result, dict):
            if isinstance(json_result.get("citations"), list):
                citations.extend([c for c in json_result["citations"] if isinstance(c, dict)])
            if isinstance(json_result.get("mentions"), list):
                mentions.extend([m for m in json_result["mentions"] if isinstance(m, dict)])
            if isinstance(json_result.get("conditions"), list):
                conditions.extend([c for c in json_result["conditions"] if isinstance(c, dict)])

    return citations, mentions, conditions, tool_run_ids, errors
