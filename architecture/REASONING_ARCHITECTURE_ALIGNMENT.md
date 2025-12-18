# Reasoning Architecture Alignment

This repo’s specification is intended to align with the published “Reasoning Architecture” for The Planner’s Assistant:
`https://theplannersassistant.uk/#/reasoning-architecture`

The published model describes a **Layered Cognitive Stack**:
**Senses → Orchestration → Applications**, anchored by **Governance**.

This repo uses different naming (ingestion/KG/grammar/dashboard), but the mapping is direct.

## 1) Canonical invariants (this repo)
* **Grammar-first**: judgement outputs are produced via the frozen 8‑move grammar (`grammar/GRAMMAR.md`) and logged as `MoveEvent`s.
* **Traceability**: evidence atoms vs interpretations vs assumptions are separate objects; tool/model calls are logged as `ToolRun`.
* **No hybrid runtime**: a deployment selects exactly one provider profile (`profiles/azure.yaml` or `profiles/oss.yaml`).
* **Dashboard is the UI**: the Digital Case Officer / dashboard IA is canonical (`ux/DASHBOARD_IA.md`).

## 2) Stack mapping

### 2.1 Applications (user-facing workspaces)
Published components:
* Scenario Workspace
* Assessment Support
* Monitoring

Repo alignment:
* Dashboard IA + modes (`ux/DASHBOARD_IA.md`)
* Scenario tabs = **Scenario × Political Framing** (`schemas/ScenarioSet.schema.json`, `schemas/ScenarioFramingTab.schema.json`)
* Judgement sheets (`schemas/ScenarioJudgementSheet.schema.json`) rendered deterministically (`render/HTML_COMPOSER_SPEC.md`)

### 2.2 Orchestration (reasoning engine + connective tissue)
Published components:
* Integration Layer (BOPS/PlanX/ODP)
* Agentic / LLM Conductor

Repo alignment:
* Connectors + public data acquisition (`integration/CONNECTORS_SPEC.md`, `integration/PUBLIC_DATA_SPEC.md`)
* 8‑move orchestrator (`agents/GRAMMAR_ORCHESTRATION_SPEC.md`) running over typed tools and producing move logs
* Provider abstraction enforcing profile purity (`platform/PROVIDER_INTERFACES.md`)

Note on “model routing”:
* the public architecture describes routing across model types; this repo enforces **no hybrid runtime**,
  so routing happens **within the active profile** (e.g., small/large LLM, text vs VLM, reranker vs embedder),
  never across Azure/OSS at runtime.

### 2.3 Senses (evidence/perception layers)
Published components:
* Policy & Knowledge Base
* Spatial Analysis Engine
* Visual Context Layer

Repo alignment:
* **Policy & Knowledge Base**
  - document parity + policy-atom chunking (`ingest/PIPELINE_SPEC.md`)
  - hybrid retrieval frames + relevance narratives (`ingest/RETRIEVAL_INDEX_SPEC.md`)
  - clause-aware citeability (`schemas/PolicyClause.schema.json`, `schemas/EvidenceRef.schema.json`)
* **Spatial Analysis Engine**
  - GIS ingestion + layer metadata (`ingest/PIPELINE_SPEC.md`)
  - spatial enrichment + site fingerprints (Slice C: `tests/SLICES_SPEC.md`)
  - KG edges for intersects/distances (`kg/KG_SCHEMA.md`)
* **Visual Context Layer**
  - visual assets + segmentation + registration (`ingest/VISUAL_SPEC.md`, `ingest/PLAN_REALITY_SLICE_B_SPEC.md`)
  - visuospatial canvases (map/plan/photomontage) (`ux/VISUOSPATIAL_WORKBENCH_SPEC.md`)

### 2.4 Governance (auditability + resilience)
Published components:
* Interface & Audit Layer
* Deployment Scaler

Repo alignment:
* Event/audit logging (`schemas/AuditEvent.schema.json`, `db/DDL_CONTRACT.md`)
* Snapshot/diff support (“what was known when?”) (`schemas/Snapshot.schema.json`, `schemas/SnapshotDiff.schema.json`, `db/DDL_CONTRACT.md`)
* Reasonableness linter (`governance/REASONABLENESS_LINTER_SPEC.md`)
* Replayability definition (render replay) (`tests/REPLAYABILITY_SPEC.md`)
* Two full deployment profiles (Azure vs OSS) with no hybrid runtime (`profiles/*.yaml`)
