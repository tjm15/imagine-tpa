# Grammar of Planning Judgement


This document defines the 8-move grammar that guides the system's logic.
The grammar is a **procedural scaffold**, not a deterministic algorithm; agents should not overfit to it.

Canonical alignment: `grammar/GRAMMAR_ALIGNMENT.md` defines the non-linear, trajectory-based
use of this grammar and the controlled vocabulary for backtracking.

## 1. Framing
**Goal**: Establish the "lens" for the session.
* **Inputs**: User intent, CULP stage, specific "Political Framing" selection (e.g., "Maximize Housing Delivery", "Protect Green Belt"), Anchors.
* **Outputs**: `Framing` object with purpose, scope, distinct goals/non-goals, and initial `Assumptions`.

## 2. Issue Surfacing
**Goal**: Identify what is material to this framing.
* **Mechanism**: Abductive reasoning over the Knowledge Graph (KG).
* **Outputs**: `Issue[]` list, `IssueMap` (relationships).
* **Key**: Includes "why material" and "initial evidence hooks".

## 3. Evidence Curation
**Goal**: Gather the facts required to assess the issues.
* **Mechanism**: Retrieval (vector/hybrid/FTS) + Graph Traversal.
* **Outputs**: `CuratedEvidenceSet` (atoms mapped to issues), `DeliberateOmissions` (what was ignored), `ToolRequest[]` (to fill gaps).

## 4. Evidence Interpretation (The Reasoning Engine)
**Goal**: Make sense of the evidence employing statutory tests and heuristics.
* **Mechanism**: LLM/VLM reasoning + Spatial Tools.
* **Outputs**: `Interpretation[]`, `ReasoningTrace[]`, `PlanRealityInterpretation`.
* **Constraint**: Must distinguish facts from inferences. Lawfulness checks should use available heuristics when present.

## 5. Considerations Formation (The Ledger)
**Goal**: Produce the "bricks" of the argument.
* **Mechanism**: Synthesis of Interpretations against Policy.
* **Outputs**: `ConsiderationLedgerEntry[]`.
* **Key**: A consideration links `Interpretation` -> `PolicyClause`. Flag explicit **Tensions** between policies.

## 6. Weighing & Balance
**Goal**: Assign weight to considerations under the current framing.
* **Mechanism**: Execution of **Statutory Balance Patterns** (Straight, Tilted, Heritage, Green Belt).
* **Outputs**: `WeighingRecord` (trade-offs, decisive factors), `ReasoningTrace[]`.
* **Input**: Must explicitly select the `BalancingMode` based on triggers (e.g., 5YHLS inputs).

## 7. Negotiation & Alteration
**Goal**: Propose changes to resolve conflicts or improve the balance.
* **Mechanism**: "What if?" reasoning.
* **Outputs**: `NegotiationMove[]` (proposed tweaks to boundaries, wording, phrasing).

## 8. Positioning & Narration
**Goal**: Tell the story.
* **Mechanism**: Narrative generation conditional on the Framing and Weighing.
* **Outputs**: `Trajectory` + `ScenarioJudgementSheet` per **Scenario × Political Framing** tab.
* **Key**: "Under framing X, for scenario S, a reasonable position is Y..."

## ReasoningTrace (TraceBundle)
`ReasoningTrace[]` entries are **trace bundles** that make reasoning inspectable without forcing determinism.
They should reference:
* `context_bundle_ref`
* `tool_run_ids`
* `prompt_id` / `prompt_version` entries used by tools
* optional forensic reasoning artefacts (stored separately from UI outputs)

ReasoningTrace is for planner‑friendly visualization (trace canvas), not for enforcing a single chain of thought.

## Roadmap (Planned Reasoning Patterns)
Planned patterns and heuristics (not yet canonical):
* Operational tests (Flood, Ecology, Retail)
* Case law heuristics (Fallback, Hillside, Finney)
