# Reasoning Chain (UI) Specification
> WARNING: This spec is provisional/outdated/incomplete. TODO: review and update.

The dashboard uses a 7-step **Reasoning Chain** to organise and navigate capability modules:
`Evidence → Context → Patterns → Options → Tests → Judgement → Explanation`.

This is an interaction model (UX). It must not replace or modify the frozen 8‑move grammar in `grammar/GRAMMAR.md`.

## 1) Mapping to the 8-move grammar
The chain provides a planner-friendly navigation layer over the grammar:

* **Evidence** → primarily Move 3 (Evidence curation) and ingestion/tooling that produces evidence atoms
* **Context** → primarily Move 1 (Framing) + Move 2 (Issue surfacing) inputs
* **Patterns** → primarily Move 2 (Issue surfacing) + early Move 4 (Interpretation) pattern recognition
* **Options** → primarily Move 7 (Negotiation & alteration) and scenario generation/deltas
* **Tests** → primarily Move 4 (Evidence interpretation) + Move 5 (Considerations formation) + operational tests
* **Judgement** → primarily Move 6 (Weighing & balance)
* **Explanation** → primarily Move 8 (Positioning & narration) + deterministic rendering from structured outputs

## 2) Capability cards
Each chain phase surfaces one or more **capability cards** from `capabilities/CAPABILITIES_CATALOGUE.yaml`.

Each card must be able to show:
* what evidence it used (EvidenceCards)
* what tools were invoked (ToolRuns)
* what it produced (structured outputs)
* what assumptions were introduced (Assumptions)
* what uncertainty remains (small list)

## 3) Scenario × Framing tabs (Spatial Strategy)
In Spatial Strategy, the chain operates over a scenario workspace where the primary comparison surface is **Scenario × Political Framing** tabs:
* **Scenario** provides the state vector (option definition).
* **Framing** provides the political lens for weighing and narration.
* Each tab produces one `Trajectory` + `ScenarioJudgementSheet`, backed by its own run log.
