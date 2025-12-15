# Grammar Orchestration Specification

## The "Loop"
The orchestrator must run the 8 moves in sequence.
Backtracking is allowed but must be explicit (new `MoveEvent` with `type="negotiation"` leading back to `weighing`).

## Agent Roles
* **Scout**: Finds evidence (Retrieval + KG).
* **Analyst**: Interprets evidence (Interpretation).
* **Judge**: Weighs considerations (Weighing).
* **Scribe**: Writes the narrative (Narrative).

## Tool Calling
Agents do NOT hallucinate data. They CALL tools:
* `get_policy_stack(...)`
* `get_site_fingerprint(...)`
* `get_visual_evidence(...)`
