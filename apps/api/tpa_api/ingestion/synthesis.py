from __future__ import annotations

from typing import Any, Dict, List
from tpa_api.ingestion.policy_extraction import run_llm_prompt


def imagination_synthesis(
    document_id: str,
    policies: List[Dict],
    visuals: List[Dict],
    run_id: str | None = None
) -> Dict[str, Any]:
    """
    The final 'Imagination' pass - linking text and visuals to infer new metadata.
    Renamed from _llm_imagination_synthesis.
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
    
    obj, tool_run_id, errs = run_llm_prompt(
        prompt_id="planner_imagination_v2",
        prompt_version=2,
        prompt_name="Planner Imagination",
        purpose="Synthesize cross-modal planning implications",
        system_template=system_template,
        user_payload=user_payload,
        output_schema=None,
        run_id=run_id
    )
    
    return obj or {}
