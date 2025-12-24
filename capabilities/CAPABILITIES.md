# Capabilities Specification (Planner’s Assistant)

This repo targets a single civic reasoning engine expressed in **three pipelines**:
1. **Spatial Strategy** (plan-making / scenarios)
2. **Development Management** (casework)
3. **Monitoring & Delivery** (live monitoring + statutory reporting)

The public “Capabilities” page describes these as a **Reasoning Chain** with 7 UI phases:
`Evidence → Context → Patterns → Options → Tests → Judgement → Explanation`.

## 1) What this document freezes
* A canonical, versioned catalogue of capabilities: `capabilities/CAPABILITIES_CATALOGUE.yaml`.
* A rule that the **Reasoning Chain is a UI navigation model**, not a replacement for the frozen **8‑move grammar** in `grammar/GRAMMAR.md`.

## 2) How capabilities map onto the grammar
Capabilities are implemented as workflows that:
* read evidence atoms from the canonical store + KG,
* call tools/instruments (logged as `ToolRun`),
* produce structured judgement artefacts and/or document drafts,
* surface in the dashboard as cards and “insertable” evidence objects.

The grammar remains the only way the system produces judgement outputs:
* `MoveEvent` logs are mandatory (`schemas/MoveEvent.schema.json`)
* provenance is mandatory (`db/PROVENANCE_STANDARD.md`)
* governance linting is mandatory (`governance/REASONABLENESS_LINTER_SPEC.md`)

Scenario comparison in Spatial Strategy is done via **tabs representing Scenario × Political Framing** combinations. Each tab runs the grammar under a specific framing for a specific scenario, producing a `Trajectory` and `ScenarioJudgementSheet` for that combination (with cached results allowed only when provenance is explicit).

## 3) Implementation contract
For every capability entry in `capabilities/CAPABILITIES_CATALOGUE.yaml`:
* there must be an executable workflow (profile-specific providers allowed, no hybrid runtime)
* the workflow must emit `ToolRun` records for tool/model calls
* outputs must be renderable in the dashboard (Living Document and/or Judgement Mode)
