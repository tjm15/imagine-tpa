import json
from typing import List, Dict, Any
from tpa_api.model_clients import _vlm_json_sync
from tpa_api.observability.phoenix import trace_span
from tpa_api.prompting import _llm_structured_sync

def _vlm_enrich_visual_asset(
    asset: Dict[str, Any],
    file_bytes: bytes,
    *,
    run_id: str | None = None,
) -> Dict[str, Any]:
    """
    High-level reasoning pass for a visual asset.
    """
    prompt = """You are a Senior Planning Officer and Spatial Analyst.
Analyze this visual asset with planner-grade care. Identify what it IS, and what it IMPLIES,
but only from visible cues. Do not invent policy codes, toponyms, or layers unless explicitly
visible or labelled.

Output JSON strictly matching this schema:
{
  "asset_category": "proposals_map|constraints_map|masterplan|technical_diagram|illustrative_render|photo|other",
  "map_scale_declared": "string or null (e.g., '1:1250')",
  "orientation": "north_up|rotated|unknown",
  "detected_layers": [
    {
      "layer_name": "string",
      "layer_type": "constraint|allocation|administrative|context|infrastructure",
      "representation_style": "polygon_fill|hatching|boundary_line|point_symbol",
      "color_hex_guess": "string or null",
      "is_legend_item": true
    }
  ],
  "extracted_toponyms": ["string"],
  "linked_policy_codes": ["string"],
  "legibility_score": 0.0,
  "interpretation_notes": "Concise planner-grade commentary on ambiguity, limitations, or key cues."
}

Rules:
- Use null for map_scale_declared when not explicitly shown.
- Use "unknown" orientation if no north arrow/compass/grid cue is visible.
- Only include linked_policy_codes if the code is visible in the image.
- color_hex_guess must be a best-effort 6-digit hex (e.g. '#AABBCC') or null.
- Keep interpretation_notes short and grounded in visible evidence.
"""
    
    span_attrs = {
        "tpa.tool": "vlm_enrich_visual_asset",
        "tpa.run_id": run_id,
        "tpa.visual_asset_id": asset.get("visual_asset_id"),
        "tpa.asset_type": asset.get("asset_type"),
    }
    with trace_span("vlm.visual_enrich", span_attrs) as span:
        obj, errs = _vlm_json_sync(prompt=prompt, image_bytes=file_bytes)
        if errs and span is not None:
            span.set_attribute("tpa.errors", ";".join(errs[:5]))
    return obj or {}

def _llm_enrich_policy_structure(document_title: str, blocks: List[Dict[str, Any]], run_id: str) -> List[Dict[str, Any]]:
    """
    Deep semantic extraction of policy structure.
    Aggregates blocks into a coherent chapter analysis first, then extracts atoms.
    """
    full_text = "\n\n".join([b.get('text', '') for b in blocks if b.get('text')])
    
    system_template = """You are a Senior Planning Policy Analyst.
Extract a machine-readable policy model from this text. Focus on planner-legible policy atoms:
Triggers (IF/WHERE), Requirements (THEN/MUST), and Exceptions (UNLESS).

Output JSON strictly matching:
{
  "policies": [
    {
      "policy_code": "string",
      "clause_ref": "string",
      "intent": "strategic_objective|development_management|site_allocation|implementation",
      "triggers": [
        {
          "trigger_type": "spatial_zone|development_scale|development_use|temporal_event|feature_presence",
          "raw_text": "string",
          "normalized_value": "string|number|null",
          "spatial_layer_ref": "string|null"
        }
      ],
      "requirements": [
        {
          "modality": "must|should|support|resist|prohibit|require_contribution",
          "requirement_type": "performance_standard|submission_item|financial_contribution|physical_provision|design_principle",
          "raw_text": "string",
          "target_metric": "string|null",
          "target_value": "number|null",
          "target_unit": "string|null",
          "target_operator": "min|max|exact|approx"
        }
      ],
      "exceptions": [
        {
          "exception_type": "viability|technical_feasibility|better_alternative|temporary_use",
          "description": "string"
        }
      ],
      "defined_terms": ["string"],
      "legislation_refs": ["string"],
      "related_policies": ["string"]
    }
  ]
}

Rules:
- Keep arrays empty if there is no evidence in the text.
- Do not invent policy codes or clause refs if not present.
- Use raw_text for exact clause wording; keep interpretations out of raw_text.
"""
    
    user_payload = {
        "document_title": document_title,
        "text": full_text
    }
    
    prompt_id = "rich_policy_structure_v2"
    
    obj, tool_run_id, errs = _llm_structured_sync(
        prompt_id=prompt_id,
        prompt_version=2,
        prompt_name="Rich Policy Extraction",
        purpose="Extract Planner-Legible Policy Atoms",
        system_template=system_template,
        user_payload=user_payload,
        output_schema_ref=None,
        run_id=run_id
    )
    
    if obj and "policies" in obj:
        return obj["policies"]
        
    return []

def _llm_imagination_synthesis(document_id: str, policies: List[Dict], visuals: List[Dict], run_id: str) -> Dict[str, Any]:
    """
    The final 'Imagination' pass - linking text and visuals to infer new metadata.
    """
    system_template = """You are the Lead Planning Inspector.
Synthesize extracted policies and visual assets to surface planner-useful cross-modal cues.
Stay grounded in the provided evidence summaries. Do not invent new facts.

Your task:
1. Identify which policies are visualized by which maps/diagrams.
2. Spot contradictions or tensions (e.g., text says "protect" but map shows "allocation").
3. Propose planner-relevant questions and scenario levers this document enables.
4. Flag evidence gaps where a planner would need another artefact or check.

Output JSON:
{
  "cross_modal_links": [{"policy_code": "string", "asset_id": "uuid", "rationale": "string"}],
  "potential_conflicts": [{"description": "string", "severity": "high|medium|low"}],
  "qa_seeds": ["string"],
  "planner_query_seeds": ["string"],
  "scenario_levers": ["string"],
  "evidence_gaps": ["string"]
}
"""
    
    user_payload = {
        "policies": policies,
        "visuals": visuals
    }
    
    obj, tool_run_id, errs = _llm_structured_sync(
        prompt_id="planner_imagination_v2",
        prompt_version=2,
        prompt_name="Planner Imagination",
        purpose="Synthesize cross-modal planning implications",
        system_template=system_template,
        user_payload=user_payload,
        output_schema_ref=None,
        run_id=run_id
    )
    
    return obj or {}
