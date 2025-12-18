# Implementation Plan (Productising the AI‑Augmented Planning Workbench)

This plan is intentionally **workbench-shaped**, not pipeline-shaped.
TPA is not “run a workflow and get an answer”; it is a **planning IDE** where agents continuously help assemble context, draft, test, and narrate — while the planner remains the decision-maker and the system remains contestable.

**Success criterion**: the product behaves like a defensible planning file aligned to the GOV.UK 30‑month local plan process (`culp/PROCESS_MODEL.yaml`), producing:
* fast drafts that planners can actually work with (Living Document),
* Scenario × Political Framing comparisons (Judgement Mode),
* graphical traceability (Trace Canvas),
* and a replayable procedure log (8‑move grammar) with provenance.

This repo keeps three non‑negotiables:
* **Grammar-first judgement** (`grammar/GRAMMAR.md`, `schemas/MoveEvent.schema.json`)
* **Provenance-first evidence** (`schemas/EvidenceRef.schema.json`, `schemas/ToolRun.schema.json`)
* **Two complete, non-hybrid deployments** (`profiles/*.yaml`, `platform/PROVIDER_INTERFACES.md`)
* **CULP artefacts are hard requirements** (stage gating via `culp/PROCESS_MODEL.yaml`, `culp/ARTEFACT_REGISTRY.yaml`, `schemas/CulpArtefactRecord.schema.json`)

---

## 1) Define the “planner moments” (north-star loops)
The build is driven by a small set of loops that must feel right to planners — everything else is downstream engineering.

### Loop A — “Draft a place portrait” (Spatial Strategy)
Planner action:
* open a `PlanProject` at `baselining_and_place_portrait`
* click **Draft → Place portrait**

System behaviour:
* agents acquire/curate baseline evidence (public data + authority docs) as EvidenceCards
* draft an editable `AuthoredArtefact` with citations and explicit assumptions
* surface a Trace Canvas flowchart showing what was used and what’s missing

Deliverable:
* a citeable draft, not a “report generator output”

### Loop B — “Compare spatial strategy options under different framings”
Planner action:
* create or request scenario options; choose political framing preset(s)
* switch tabs (Scenario × Political Framing) in Judgement Mode

System behaviour:
* run the full 8-move grammar per tab (non-deterministic allowed) and store outputs
* render sheets deterministically and show “what changed / why it matters”
* keep minority/alternative issues visible when plausible (reasonable disagreement)

Deliverable:
* tabbed sheets that feel like planning judgement, not a dashboard

### Loop C — “Draft a policy clause (and defend it)”
Planner action:
* highlight a paragraph in the plan chapter; click **Draft → Policy clause**

System behaviour:
* propose clause wording + justification + evidence bindings
* any recommendation-like claim either links to an existing grammar run or triggers one
* planner can accept/reject suggestions; everything is auditable

Deliverable:
* policy drafting that preserves the golden thread from evidence → strategy → wording

### Loop D — “Open a real case and get a usable report draft” (DM)
Planner action:
* open inbox (PlanIt seeded) → open case → Draft officer report section(s)

System behaviour:
* assemble context (policy + constraints + history) and draft with citations
* maintain an audit trail; never silently “decide”

Deliverable:
* a real case file that reduces admin load without destroying defensibility

These loops are the product. The rest of this plan exists to make them possible.

---

## 2) Build the Workbench Kernel (the minimum “planning IDE” substrate)
The kernel is what makes TPA feel like a workbench rather than a chatbot.

### 2.1 Core objects (persisted, not ephemeral)
* `PlanProject` (Spatial Strategy workspace anchor): `schemas/PlanProject.schema.json`
* `AuthoredArtefact` (Living Document): `schemas/AuthoredArtefact.schema.json`
* `Scenario/ScenarioSet/ScenarioFramingTab`: `schemas/Scenario*.schema.json`
* `Application` + `PreApplication` for DM: `schemas/Application.schema.json`, `schemas/PreApplication.schema.json`

### 2.2 Event + job model (agents live inside the workbench)
* everything is triggered by explicit events (user, agent, system): `schemas/AuditEvent.schema.json`
* everything that touches evidence/tools/models is a logged run: `schemas/ToolRun.schema.json`
* judgement is persisted as move outputs: `schemas/MoveEvent.schema.json`
* run history and snapshots support “what was known when?” (`db/DDL_CONTRACT.md`)

### 2.3 UI surfaces (the four screens that matter)
* Strategic Home (CULP timeline + stage gating): `ux/DASHBOARD_IA.md`, `culp/PROCESS_MODEL.yaml`
* Living Document (WYSIWYG + citations + suggestions): `ux/UI_SYSTEM_SPEC.md`
* Judgement Mode (tabs + sheets + evidence drill-down): `ux/DASHBOARD_IA.md`
* Trace Canvas (graphical traceability): `ux/TRACE_CANVAS_SPEC.md`

Visuospatial reasoning surfaces (non-optional):
* Map / Plan / Photomontage canvases: `ux/VISUOSPATIAL_WORKBENCH_SPEC.md`
* Visual context ingestion + overlays: `ingest/VISUAL_SPEC.md`, `ingest/PLAN_REALITY_SLICE_B_SPEC.md`, `render/MAP_OVERLAY_SPEC.md`

Kernel acceptance:
* Loop A and Loop B can run against fixture evidence with stored runs and a working Trace Canvas.

---

## 3) Build the Agent Runtime (interactive, incremental, tool-bound)
If agents are “a careful colleague”, the runtime must behave like a colleague:
* incremental updates (not one giant blocking run)
* explicit limitations and assumptions
* safe defaults (no uncited claims)

### 3.1 Orchestrator behaviour
* runs are per Scenario × Political Framing tab (Spatial Strategy) (`agents/GRAMMAR_ORCHESTRATION_SPEC.md`)
* drafting is time-budgeted and suggestion-based (`agents/DRAFT_LAUNCHER_SPEC.md`)
* agents explore via typed tools (no rummaging), and every call is a `ToolRun`

### 3.2 Governance is how we “bound” non-deterministic agents
* provenance hard checks + prompt versioning (`governance/REASONABLENESS_LINTER_SPEC.md`)
* replayability means “re-render from stored artefacts”, not deterministic prose (`tests/REPLAYABILITY_SPEC.md`)

Runtime acceptance:
* Loop A produces a draft + trace with no uncited claims (or explicit assumptions).

---

## 4) Build the Evidence Substrate (institutional memory)
The workbench is only as good as its evidence layer.

### 4.1 Authority document ingestion (clause-aware, citeable)
* chunking/atomisation that supports planner-shaped retrieval (`ingest/PIPELINE_SPEC.md`, `ingest/RETRIEVAL_INDEX_SPEC.md`)
* hybrid retrieval treated as an evidence instrument (`platform/PROVIDER_INTERFACES.md`)

### 4.2 Spatial substrate (constraints + fingerprints)
* ingest GIS sources + public data; normalise to canonical tables and KG
* precompute site fingerprints (Slice C) for fast scenario evaluation (`tests/SLICES_SPEC.md`)

### 4.3 Visual context substrate (maps/plans/photos/photomontages)
* ingest and index visual assets as citeable evidence (`schemas/VisualAsset.schema.json`)
* extract visual features/masks for plan reading and registration (`schemas/VisualFeature.schema.json`, `schemas/SegmentationMask.schema.json`)
* create transforms and overlays with explicit uncertainty (`schemas/Transform.schema.json`, `schemas/ProjectionArtifact.schema.json`)

Evidence acceptance:
* Loop B can retrieve and cite relevant policies/constraints reliably for the selected authorities.

---

## 5) Build “Scenario Workspace” as the first real product pillar (Spatial Strategy first)
Spatial strategy is upstream. If it works, everything downstream becomes easier.

### 5.1 Scenario creation and mutation (human + agent co-authoring)
* scenario state is structured (`ScenarioStateVector`) plus narrative
* mutations create deltas (what changed, why it matters)

### 5.2 Scenario × Political Framing tabs are the comparison engine
* presets in `framing/POLITICAL_FRAMINGS.yaml`
* tabs persist runs and are explicitly selected by the user (audit event)

### 5.3 Infographics that planners actually use
* build FactTables with provenance; propose FigureSpecs; render deterministically
* matrices and deltas are “planning-shaped” comparisons, not analytics dashboards

Scenario acceptance:
* Loop B yields a set of plausible, disagreeable options under explicit framings with visible trade-offs.

---

## 6) Data acquisition at scale (public sources + governed web discovery)
Scenario inputs must be gathered dynamically, but safely:
* public APIs/bulk first (`integration/PUBLIC_DATA_SPEC.md`)
* governed discovery/scraping when needed (Playwright-backed): `integration/COUNCIL_DOCUMENT_DISCOVERY_SPEC.md`

Acquisition acceptance:
* Loop A can refresh baseline inputs without manual spreadsheet work, and limitations are explicit.

## 6.1 CULP artefacts are not optional
The kernel must support producing and tracking required CULP artefacts as first-class deliverables:
* registry: `culp/ARTEFACT_REGISTRY.yaml` and `culp/ARTEFACTS_SPEC.md`
* per-project ledger: `schemas/CulpArtefactRecord.schema.json`
* UI must block/flag stages with missing required artefacts (Strategic Home stage gate panel).

---

## 7) DM mode as a second pillar (real data, schema interoperability)
DM becomes compelling when it feels like a “casework IDE” that saves time without losing defensibility.

### 7.1 Real cases for the selected authorities (PlanIt)
* authority allowlist: `authorities/SELECTED_AUTHORITIES.yaml`
* mapping: `integration/PLANIT_AUTHORITY_MAP.yaml`

### 7.2 PlanX/BOPS/DPR interoperability (OSL schemas)
* interop rules: `integration/DIGITAL_PLANNING_SCHEMAS_INTEROP_SPEC.md`
* pinned + vendored schemas: `integration/OSL_SCHEMA_SOURCES.yaml`, `external_schemas/osl_digital_planning_data_schemas/README.md`
* connector specs: `integration/PLANX_CONNECTOR_SPEC.md`, `integration/BOPS_CONNECTOR_SPEC.md`, `integration/DPR_CONNECTOR_SPEC.md`

DM acceptance:
* Loop D produces a usable cited draft report section and a trace graph on a real PlanIt case.

---

## 8) Deployment reality (two complete profiles)
Build is driven by parity, not “we’ll swap later”:
1. Make OSS profile pass Loops A/B/C with slice tests A/C/E/F.
2. Implement Azure profile parity and re-run the same loop acceptance tests.

---

## Operational step (the 9 real working cases)
* The selected authorities are declared in `authorities/SELECTED_AUTHORITIES.yaml`.
* Create one `PlanProject` per authority and use those as continuous product fixtures (not just synthetic PDFs).

---

## 9) Step-by-step roadmap (UI-first, slice-gated)
This is the concrete build order that makes the system feel real early, while keeping the architecture honest.

**Rule**: every milestone must ship a planner-visible UI improvement *and* pass one or more slice acceptance tests (`tests/SLICES_SPEC.md`).

### Milestone 0 — Freeze the “contract pack”
Goal: prevent drift while letting agents stay non-deterministic.
* Freeze/confirm: `schemas/` + `db/DDL_CONTRACT.md` + `platform/PROVIDER_INTERFACES.md` + `profiles/*.yaml`.
* Freeze/confirm: grammar IO contracts (`grammar/MOVE_IO_CATALOGUE.yaml`, `schemas/MoveEvent.schema.json`).
* Freeze/confirm: CULP stage model + artefact registry (`culp/PROCESS_MODEL.yaml`, `culp/ARTEFACT_REGISTRY.yaml`).
* Acceptance: repo-level JSON/YAML schema parsing passes; slice definitions are internally consistent.

### Milestone 1 — Strategic Home becomes usable (timeline + stage gating + audit ribbon)
Goal: align to GOV.UK 30‑month process from day one.
* Implement Strategic Home UI reading `culp/PROCESS_MODEL.yaml` and showing stage gate panel from `culp/ARTEFACT_REGISTRY.yaml`.
* Add the audit ribbon contract (active run/snapshot, unresolved flags, exports).
* Acceptance: Slice F (stage gate panel + audit ribbon semantics).

### Milestone 2 — Authority evidence substrate (policy atoms that planners can cite)
Goal: “I can find the right policy in seconds.”
* Ingest one authority pack end-to-end (docs → chunks/atoms → embeddings → index) with stable `EvidenceRef`s.
* Implement Live Policy Surface in the sidebar (ranked policy gradient + explainable relevance badges).
* Acceptance: Slice A (Document → Chunk → Cite) + retrieval frame logging.

### Milestone 3 — Map is a verb (Map Canvas v0 + spatial fingerprint)
Goal: “draw-to-ask” + instant citeable map evidence.
* Implement Map Canvas v0 (draw geometry, layer toggles, snapshot to EvidenceCard).
* Implement spatial enrichment + `get_site_fingerprint(site_id)` (site fingerprints as precompute, not ad-hoc).
* Acceptance: Slice C (fingerprint) + Slice I (map snapshot export as evidence).

### Milestone 4 — Scenario workspace v0 (ScenarioStateVector + Scenario×Framing tabs)
Goal: make strategy comparison the centre of gravity.
* Implement Scenario creation/mutation (ScenarioStateVector + lineage).
* Implement ScenarioSet and Scenario×PoliticalFraming tab generation; tab selection is always a user `AuditEvent`.
* Implement ScenarioDelta (what changed / why it matters).
* Acceptance: Slice F (tabs) + basic ScenarioSet persistence invariants.

### Milestone 5 — Judgement Mode is real (full 8-move run + deterministic sheet + Trace Canvas)
Goal: the first end-to-end “reasonable position under framing X” experience.
* Implement the grammar orchestrator per tab (`agents/GRAMMAR_ORCHESTRATION_SPEC.md`).
* Implement deterministic sheet rendering from stored outputs (`render/HTML_COMPOSER_SPEC.md`).
* Implement Trace Canvas projection (`schemas/TraceGraph.schema.json`) and “why chain” highlighting.
* Acceptance: Slice E (8 moves) + Slice F (sheet + trace flowchart) + Replayability render test (`tests/REPLAYABILITY_SPEC.md`).

### Milestone 6 — Draft-anything feels like Word (Draft launcher + suggestions + governance)
Goal: “draft-first then defend”.
* Implement DraftRequest → DraftPack workflow (`agents/DRAFT_LAUNCHER_SPEC.md`).
* Implement ghost-text/comment-bubble suggestion UI with accept/reject `AuditEvent`s.
* Implement governance linting feedback in-document (uncited claims, missing limitations).
* Acceptance: Loop A (“draft place portrait”) is usable on at least one real authority pack.

### Milestone 7 — Visuospatial becomes first-class (plans, overlays, photomontage hooks)
Goal: preserve planning judgement that happens through seeing.
* Implement Plan Canvas feature display (scale/north arrow/boundary cues).
* Implement Tier 0 registration + overlay artefacts with uncertainty (Slice B).
* Implement Reality Mode “quote what’s visible” region interpretation (caveated, logged).
* Acceptance: Slice B + Slice I (plan + photomontage evidence participates in judgement/drafting with traceability).

### Milestone 8 — Dynamic acquisition (public data + governed web discovery)
Goal: scenarios stay current without spreadsheet labour.
* Implement public data source registry pipeline (`integration/PUBLIC_DATA_SPEC.md`).
* Implement governed council discovery using Playwright-backed capture when needed (`integration/COUNCIL_DOCUMENT_DISCOVERY_SPEC.md`).
* Acceptance: at least one authority can refresh a baseline input set with archived artefacts + limitations.

### Milestone 9 — DM mode on real cases (PlanIt seed + cited report drafting)
Goal: prove the same workbench supports casework without losing defensibility.
* Implement PlanIt sync for the selected 9 authorities (`integration/PLANIT_CONNECTOR_SPEC.md`).
* Implement Application Workspace draft actions (report sections with citations + trace).
* Acceptance: Slice G on at least one real PlanIt case (seeded).

### Milestone 10 — Monitoring & delivery loop (baseline → trends → AMR draft)
Goal: close the “plan ↔ reality” loop as institutional memory.
* Implement adoption baseline snapshot + monitoring time series ingestion.
* Implement AMR drafting via FactTables + FigureSpecs.
* Acceptance: Slice H with traceable numbers and exportable monitoring narrative.

### Profile parity rule (no hybrid runtime)
Build order is:
1. Make **OSS** pass the milestone acceptance checks (fast local iteration).
2. Add **Azure** parity providers and re-run the same acceptance checks with `profiles/azure.yaml`.
