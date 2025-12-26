# PESE Implementation Plan (Planning Exploration and Structuring Environment)

PESE is a third product pillar alongside Plan-Making (Scenario Workspace) and Development Management (DM).
It introduces a standalone "Pre-Application Studio" mode in the UI that reuses the shared backend services
policy KB, spatial engine, scenario kernel, agent runtime, render pipeline, and provenance tooling.

PESE is governed by the same non-negotiables as the rest of TPA:
* Frozen 8-move grammar for judgement (`grammar/GRAMMAR.md`, `schemas/MoveEvent.schema.json`).
* Evidence and provenance as first-class objects (`db/PROVENANCE_STANDARD.md`, `schemas/ToolRun.schema.json`).
* External models are treated as evidence instruments (logged inputs, outputs, limitations).
* Two non-hybrid deployment profiles (`profiles/azure.yaml`, `profiles/oss.yaml`).

---

## 1) Architectural alignment and integration strategy
PESE is implemented as a new "Pre-Application Studio" mode that:
* is standalone in UI routing, but shares the same Workbench Kernel (events, snapshots, traces);
* reuses Scenario Workspace primitives (`schemas/Scenario*.schema.json`) for proposal state and deltas;
* extends DM interoperability for pre-application objects (`schemas/PreApplication.schema.json`);
* reuses the agent stack for issue surfacing, assessment, and delta reasoning.

Design principle: PESE extends existing systems rather than inventing parallel ones. Any new capability
should be exposed via shared services so Plan-Making and DM can consume the same assets and traces.

---

## 2) Stage 1 (MVP) - Foundations of the Pre-Application Studio
Goal: a single-user pre-application workspace that structures inputs, runs lightweight checks, and produces
traceable pre-app advice output.

### 2.1 Core product scope
* New UI route and workspace mode: "Pre-App Studio".
* Pre-app case creation and updates as explicit events (`schemas/AuditEvent.schema.json`).
* Minimal scenario state: current proposal as a scenario vector + baseline scenario.
* Constraint synthesis from uploaded documents and policy KB.
* Lightweight, traceable agent outputs (issue list, initial assessment).
* Structured pre-app advice summary, cited and auditable.

### 2.2 Backend and data model
* Add pre-app case endpoints (e.g. `POST /preapp`, `PATCH /preapp/{id}`) in FastAPI.
* Persist a PreApp case that links:
  - `PreApplication` metadata (`schemas/PreApplication.schema.json`),
  - Scenario lineage (`schemas/Scenario.schema.json`, `schemas/ScenarioDelta.schema.json`),
  - Negotiation log entries (new schema to be defined).
* Use Celery for any long-running doc parsing and extraction.

### 2.3 Agent and reasoning reuse
* Constraint and policy inference via the existing ingestion and policy KB passes.
* Scenario kernel checks (policy conflicts, infeasibilities) reuse existing scenario logic.
* Issue list from the material considerations agent, scoped to pre-app context.
* Negotiation delta tracking uses ScenarioDelta and existing delta/assessment logic.
* Pre-app summary uses the officer report generator with a dedicated template.

### 2.4 MVP UI surfaces
* Issues and Constraints panel with evidence citations.
* Proposal and Scenarios panel with editable parameters and rerun hooks.
* Notes/Discussion panel for negotiation entries and queries.
* Pre-App Summary output view with cited reasoning and limitations.

### 2.5 Stage 1 deliverables
* UI: Pre-App Studio route and initial workspace.
* API: create/update pre-app case endpoints.
* DB: new tables for pre-app case and negotiation log, linked to scenarios.
* Agents: minimal pre-app orchestration run (issue list + delta tracking).
* Output: a cited Pre-App Advice Summary.

---

## 3) Stage 2 (Intermediate) - Collaborative negotiation and richer surfaces
Goal: multi-party collaboration with explicit negotiation moves and multiple synchronized reasoning surfaces.

### 3.1 Real-time collaboration
* Introduce WebSocket channels for live updates.
* Role flags (planner, developer, specialist) to control visibility of internal notes.
* Session state is shared but auditable; all edits are logged as AuditEvents.

### 3.2 Negotiation moves and versioned proposals
* Every change creates a new Scenario node, linked via lineage.
* ScenarioDelta objects capture changes and auto-generated delta summaries.
* UI presents a timeline or branching tree of proposals for comparison.

### 3.3 Four reasoning surfaces (synchronized)
* Planning surface: policy applicability, conflicts, and trade-offs.
* Design surface: spatial editing and parameter controls tied to scenario state.
* Negotiation surface: conditional offers, issue tracker, and agreement status.
* Viability surface: parsed assumptions and what-if calculations (transparent, cited).

### 3.4 Enhanced agent pipeline
* Introduce a negotiation reasoning agent to extract conditional statements.
* Viability agent parses pro-forma inputs and runs controlled what-if tests.
* Shared state manager collects current scenario, constraints, and negotiation state
  to keep all surfaces consistent.

### 3.5 Stage 2 deliverables
* WebSocket collaboration for shared sessions.
* Scenario versioning UI with delta summaries.
* Four surface UI with synchronized updates.
* Extended agent orchestration with traceability to evidence.

---

## 4) Stage 3 (Full integration) - Production-ready PESE
Goal: robust multi-party workflows, institutional integration, and full traceability.

### 4.1 Multi-party and institutional integration
* Authn/authz for external participants, per-session access controls.
* Link pre-app sessions to DM Applications and site records for institutional memory.
* Pre-app graph exports into Application Graph Store when formal applications arrive.

### 4.2 Expanded viability and simulation
* Optional quantitative viability modeling (residual value, IRR, cost baselines).
* Heavy simulations run as asynchronous jobs with explicit limitations.
* Support parallel scenario branches without forcing single-score optimization.

### 4.3 Full traceability and non-flattening of considerations
* Forensic trace mode (graph view) for evidence and reasoning lineage.
* Keep contradictory considerations visible; do not collapse to a single metric.
* Explicit uncertainty flags and assumption prompts in the UI.

### 4.4 Stage 3 deliverables
* Production-ready collaboration with identity integration.
* PESE session records are accessible in DM and Plan-Making workflows.
* Trace graph support for inspectors and audit requirements.
* Governance checks for external-facing outputs (reasonableness linting).

---

## 5) Cross-cutting requirements
* All PESE outputs must use the frozen 8-move grammar and be logged as MoveEvents.
* External model calls are logged as ToolRuns with prompt and limitation metadata.
* PESE must run in both provider profiles without hybrid runtime behavior.
* Evidence traceability is mandatory for any cited policy, constraint, or map overlay.
