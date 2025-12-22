from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel
from datetime import datetime
import uuid
import json

from tpa_api.retrieval import _retrieve_policy_clauses_hybrid_sync
from tpa_api.model_clients import _generate_completion_sync

class MoveType(str, Enum):
    FRAMING = "framing"
    ISSUE_SURFACING = "issue_surfacing"
    EVIDENCE_CURATION = "evidence_curation"
    EVIDENCE_INTERPRETATION = "evidence_interpretation"
    CONSIDERATIONS_FORMATION = "considerations_formation"
    WEIGHING_AND_BALANCE = "weighing_and_balance"
    NEGOTIATION_AND_ALTERATION = "negotiation_and_alteration"
    POSITIONING_AND_NARRATION = "positioning_and_narration"

class MoveEvent(BaseModel):
    move_id: str
    run_id: str
    move_type: MoveType
    timestamp: datetime
    output_artifacts:  Dict[str, Any]
    evidence_refs: List[str]
    reasoning_trace: str

class GrammarOrchestrator:
    def __init__(self, run_id: str, political_framing: str):
        self.run_id = run_id
        self.political_framing = political_framing
        self.evidence_context: List[Dict[str, Any]] = []

    async def execute_move(self, move_type: MoveType, input_context: Dict[str, Any], authority_id: str = "default") -> MoveEvent:
        print(f"[{self.run_id}] Executing real move: {move_type}")
        
        # 1. SPECIAL: Evidence Curation (Move 3)
        evidence_refs: List[str] = []
        if move_type == MoveType.EVIDENCE_CURATION:
            # Analyze input context (issues) to form queries
            issues = input_context.get("issues", [])
            query = f"Policies regarding {self.political_framing}"
            if issues:
                query += " " + " ".join([i.get("title", "") for i in issues])
            
            print(f"  -> Retrieving evidence for query: {query[:50]}...")
            
            # Use Hybrid Retrieval logic
            retrieval_result = _retrieve_policy_clauses_hybrid_sync(
                query=query,
                authority_id=authority_id,
                limit=5
            )
            
            self.evidence_context = retrieval_result.get("results", [])
            for res in self.evidence_context:
                evidence_refs.append(res.get("evidence_ref", "unknown"))
            print(f"  -> Found {len(self.evidence_context)} items.")

        # 2. Build Prompt
        prompt = self._build_prompt(move_type, input_context)
        
        # 3. LLM Inference
        print("  -> Calling LLM...")
        raw_output = _generate_completion_sync(prompt=prompt) or "{}"
        
        # 4. Parse (Naive JSON)
        try:
            # Attempt to find JSON bloack
            if "```json" in raw_output:
                json_str = raw_output.split("```json")[1].split("```")[0]
            elif "```" in raw_output:
                json_str = raw_output.split("```")[1].split("```")[0]
            else:
                json_str = raw_output
            
            output_artifacts = json.loads(json_str)
        except Exception:
            output_artifacts = {"raw_text": raw_output, "error": "Failed to parse JSON"}

        # 5. Create Event
        event = MoveEvent(
            move_id=str(uuid.uuid4()),
            run_id=self.run_id,
            move_type=move_type,
            timestamp=datetime.utcnow(),
            output_artifacts=output_artifacts,
            evidence_refs=evidence_refs,
            reasoning_trace=f"Prompt: {prompt[:100]}... Output: {raw_output[:100]}..."
        )
        
        return event

    def _build_prompt(self, move_type: MoveType, context: Dict[str, Any]) -> str:
        base_nav = f"""You are the Planning Officer Engine.
Task: Execute Grammar Move '{move_type.value.upper()}'.
Framing: {self.political_framing}.
Current Context: {json.dumps(context, default=str)[:3000]}
"""
        
        if move_type == MoveType.FRAMING:
            return base_nav + "\nDefine the spatial strategy framing and valid scope. Output JSON: { 'framing_statement': '...', 'scope': [...] }"
            
        elif move_type == MoveType.ISSUE_SURFACING:
            return base_nav + "\nIdentify key planning issues based on the framing. Output JSON: { 'issues': [{'title': '...', 'description': '...'}] }"
            
        elif move_type == MoveType.EVIDENCE_CURATION:
            return base_nav + "\nSearch completed. Summarize the retrieval strategy used. Output JSON: { 'retrieval_summary': '...' }"
            
        elif move_type == MoveType.EVIDENCE_INTERPRETATION:
            ev_str = json.dumps([e.get("snippet", "")[:200] for e in self.evidence_context])
            return base_nav + f"\nInterpret the following evidence:\n{ev_str}\nOutput JSON: {{ 'findings': [...] }}"
            
        elif move_type == MoveType.POSITIONING_AND_NARRATION:
            return base_nav + "\nDraft the final 'Place Portrait' narrative, synthesizing all previous moves into a cohesive spatial vision statement. Output JSON: { 'place_portrait_text': '...' }"
            
        return base_nav + "\nProceed with the move. Output JSON summary."

    async def run_full_grammar(self) -> List[MoveEvent]:
        history = []
        moves = list(MoveType)
        context = {}
        
        for move in moves:
            event = await self.execute_move(move, context)
            history.append(event)
            context.update(event.output_artifacts)
            
        return history
