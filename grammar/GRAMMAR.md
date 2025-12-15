# Grammar of Planning Judgement

This document defines the 8-move grammar that dictates the system's logic.

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
* **Outputs**: `CuratedEvidenceSet` (atoms mapped to issues), `DeliberateOmissions` (what was ignored), `ToolRequests` (to fill gaps).

## 4. Evidence Interpretation
**Goal**: Make sense of the evidence (Plan ↔ Reality).
* **Mechanism**: VLM / LLM reasoning + Spatial Tools + "Slice B" (plan registration).
* **Outputs**: `Interpretation[]` (claims backed by refs), `PlanRealityInterpretation` (overlays, transform confidence).
* **Constraint**: Must distinguish *what the evidence says* from *what the agent infers*.

## 5. Considerations Formation (The Ledger)
**Goal**: Produce the "bricks" of the argument.
* **Mechanism**: Synthesis of Interpretations against Policy.
* **Outputs**: `ConsiderationLedgerEntry[]`.
* **Key**: A consideration links `Interpretation` -> `PolicyClause`. It *must* list mitigation hooks and uncertainty.

## 6. Weighing & Balance
**Goal**: Assign weight to considerations under the current framing.
* **Mechanism**: Qualitative balancing (not just adding numbers).
* **Outputs**: `WeighingRecord` (trade-offs, decisive factors).

## 7. Negotiation & Alteration
**Goal**: Propose changes to resolve conflicts or improve the balance.
* **Mechanism**: "What if?" reasoning.
* **Outputs**: `NegotiationMove[]` (proposed tweaks to boundaries, wording, phrasing).

## 8. Positioning & Narration
**Goal**: Tell the story.
* **Mechanism**: Narrative generation conditional on the Framing and Weighing.
* **Outputs**: `Trajectory[]` (Tabs), `ScenarioJudgementSheet` (The final renderable object).
* **Key**: "Under framing X, a reasonable position is Y..."
