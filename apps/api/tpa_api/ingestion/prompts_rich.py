import json
from typing import List, Dict, Any
from tpa_api.model_clients import _vlm_json_sync
from tpa_api.prompting import _llm_structured_sync

def _vlm_enrich_visual_asset(asset: Dict[str, Any], file_bytes: bytes) -> Dict[str, Any]:
    """
    High-level reasoning pass for a visual asset.
    """
    prompt = """You are a Senior Planning Officer and Spatial Analyst. 
Analyze this visual asset from a Planning Document with high levels of reasoning.
Identify not just what it IS, but what it IMPLIES for development.

Output JSON strictly matching this schema:
{
  "asset_category": "proposals_map|constraints_map|masterplan|technical_diagram|illustrative_render|photo|other",
  "map_role": "proposals|constraints|allocation|context|inset|null",
  "detected_layers": [
    {
      "layer_name": "string",
      "layer_type": "constraint|allocation|administrative|context|infrastructure",
      "representation_style": "polygon_fill|hatching|boundary_line|point_symbol"
    }
  ],
  "interpretation_notes": "Deep reasoning about the implications of this visual. Avoid hallucination.",
  "legibility_score": 0.9
}

Think like a planner: 
- Is there a red-line boundary? 
- What constraints are visible (Green Belt, Flood Zones, Heritage)?
- If it's a photo, what is the 'character' of the area?
"""
    
    obj, errs = _vlm_json_sync(prompt=prompt, image_bytes=file_bytes)
    return obj or {}

def _llm_enrich_policy_structure(document_title: str, blocks: List[Dict[str, Any]], run_id: str) -> List[Dict[str, Any]]:
    """
    Deep semantic extraction of policy structure.
    Aggregates blocks into a coherent chapter analysis first, then extracts atoms.
    """
    full_text = "\n\n".join([b.get('text', '') for b in blocks if b.get('text')])
    
    system_template = """You are a Senior Planning Policy Analyst.
Your goal is to extract a machine-readable model of the planning policies in this text.
Identify the "Policy Atoms": Triggers (Where/When), Requirements (What), and Exceptions (Unless).

Output JSON matching the 'policies' field in the schema.

Rules:
- Collapse multiple paragraphs of the same policy into one Clause if they are semantically one unit.
- Extract spatial triggers (e.g. "Within 5km of the airport") precisely.
- Normalize targets (e.g. "30%" -> 0.3).
- Engage high levels of reasoning to resolve cross-references within the text.
"""
    
    user_payload = {
        "document_title": document_title,
        "text": full_text
    }
    
    prompt_id = "rich_policy_structure_v1"
    
    obj, tool_run_id, errs = _llm_structured_sync(
        prompt_id=prompt_id,
        prompt_version=1,
        prompt_name="Rich Policy Extraction",
        purpose="Extract Planner-Legible Policy Atoms",
        system_template=system_template,
        user_payload=user_payload,
        output_schema_ref="schemas/IngestionArtifact.schema.json",
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
Synthesize the extracted policies and visual assets to identify high-leverage spatial implications.

Your task:
1. Identify which policies are visualized by which maps.
2. Spot contradictions (e.g. text says 'protect' but map shows 'allocation').
3. Suggest 3 canonical questions this document answers well for a developer.

Output JSON:
{
  "cross_modal_links": [{"policy_code": "string", "asset_id": "uuid", "rationale": "string"}],
  "potential_conflicts": [{"description": "string", "severity": "high|medium|low"}],
  "qa_seeds": ["string"]
}
"""
    
    user_payload = {
        "policies": [{"code": p.get("policy_code"), "intent": p.get("intent")} for p in policies],
        "visuals": [{"id": v.get("id"), "category": v.get("asset_category"), "notes": v.get("interpretation_notes")} for v in visuals]
    }
    
    obj, tool_run_id, errs = _llm_structured_sync(
        prompt_id="planner_imagination_v1",
        prompt_version=1,
        prompt_name="Planner Imagination",
        purpose="Synthesize cross-modal planning implications",
        system_template=system_template,
        user_payload=user_payload,
        output_schema_ref=None,
        run_id=run_id
    )
    
    return obj or {}