# UI System Specification (Dashboard / Digital Case Officer)

This document makes the UI implementable without weakening the “grammar-first, provenance-first” architecture.

The UI is not a dashboard of charts; it is a **Digital Case Officer** workspace where the primary focus is always the deliverable (policy/report/plan chapter), with maps and judgement sheets as contextual surfaces.

For planner-first workflow intent and “jobs-to-be-done”, see `ux/PLANNER_WORKFLOWS_SPEC.md`.

## 0) Two top-level workspaces (the “two modes” requirement)
The product has two primary user workspaces, each with its own navigation and default objects:

1. **Local Plan / Spatial Strategy mode**
   - Default home: **Strategic Home** (CULP timeline and gates).
   - Primary objects: plan project, scenarios, sites, policies, consultation corpora.
   - Primary comparison surface: **Scenario × Political Framing tabs** in Judgement Mode.

2. **Development Management (DM) mode**
   - Default home: **Casework Home** (inbox + statutory timelines).
   - Primary objects: applications, revisions, consultees, conditions, decisions.
   - Comparison surface: negotiation/revision deltas + (optionally) recommendation options under explicit framings.

Both modes reuse the same core UI system: Living Document editor, Evidence Shelf, Map canvas, Trace Canvas, and Draft launcher — but with different default context anchors.

## 0) UI invariants (non‑negotiable)
1. **Dashboard is canonical UI**: all work happens in the workspace described in `ux/DASHBOARD_IA.md`.
2. **Grammar-first for judgement**: any judgement output shown to users must be produced via the 8 moves (`grammar/GRAMMAR.md`) and logged (`schemas/MoveEvent.schema.json`).
3. **Non-deterministic agents are allowed**: the UI must never assume repeatable prose; it must rely on stored artefacts and re-render (`tests/REPLAYABILITY_SPEC.md`).
4. **Provenance everywhere**: any AI suggestion, chart, map output, or sentence-level claim must be traceable to `EvidenceRef` and/or a `ToolRun` (`db/PROVENANCE_STANDARD.md`).
5. **User is the selector**: Scenario × Political Framing tab selection is always an explicit, auditable event (`schemas/AuditEvent.schema.json`).
6. **Explainability modes**: the UI must support `Summary`, `Inspect`, and `Forensic` views of the same underlying run (see the published “Interface & Audit Layer”).
7. **Visuospatial reasoning is first-class**: maps, plans, policy maps, photos, and photomontages are core evidence surfaces, not optional add-ons (see `ux/VISUOSPATIAL_WORKBENCH_SPEC.md`).
8. **Snapshots support legal questions**: key stages and sign-offs must be linkable to a frozen snapshot (“what was known when?”) (`schemas/Snapshot.schema.json`).

## 0.1 Traceability must be graphical (Trace Canvas)
Traceability is experienced primarily through a **flowchart-like Trace Canvas**, not by reading JSON.
* Spec: `ux/TRACE_CANVAS_SPEC.md`
* Data: `schemas/TraceGraph.schema.json` (deterministically derived from `MoveEvent` + `ToolRun` + `AuditEvent`)

## 1) Primary surfaces (what must exist in v1)

### 1.1 Strategic Home (CULP timeline)
Purpose: keep the system aligned to the GOV.UK 30‑month local plan process (`culp/PROCESS_MODEL.yaml`).

Required UI elements:
* **Timeline / dependency chart** showing stages, blocking artefacts, and status (draft/published/blocked).
* **Stage gate panel** showing required artefacts for the selected stage and what’s missing.
  * Required artefacts are defined in `culp/PROCESS_MODEL.yaml` and catalogued in `culp/ARTEFACT_REGISTRY.yaml`.
  * Per-project artefact status is tracked via `CulpArtefactRecord` (`schemas/CulpArtefactRecord.schema.json`).
* **Run history / audit ribbon**: quick link to the active snapshot/run set used for any published artefact.
  * Snapshots are optional early on, but become mandatory for published/sign‑off states: `schemas/Snapshot.schema.json`.

### 1.1.1 Audit ribbon (cross-cutting trust surface)
The published architecture’s “Interface & Audit Layer” must be felt in the UI as a persistent, low-friction surface.

Required ribbon elements:
* active `run_id` and (when used) active `snapshot_id`
* trace count + unresolved governance flags
* one-click export controls (evidence bundle + trace graph)
* explainability mode toggle (`summary` / `inspect` / `forensic`)

### 1.2 Casework Home (DM inbox)
Purpose: manage real workloads and deadlines without losing the reasoning thread.

Required UI elements:
* **Inbox board** with case status columns (new/validating/consultation/assessment/determination/issued).
* **Deadline visibility** (days remaining, breached flags) and simple filters (ward, agent, type).
* **One-click open** into the Application Workspace (same 70/30 split layout).

### 1.2 Workspace (70/30 split)
Purpose: be a “Smart Word” environment with AI assistance that never breaks traceability.

Left (70%): the active artefact surface (Document/Map/Judgement/Reality mode toggle).
Right (30%): context sidebar (Smart Feed + Evidence Shelf + mini-map).

Modes (must be switchable without losing state):
* **Document Mode**: WYSIWYG editor for authored outputs (policies, reports, plan chapters).
* **Map Mode**: Map canvas for spatial reasoning and “draw to ask”.
* **Judgement Mode**: Scenario × Political Framing tabs; each tab shows a rendered `ScenarioJudgementSheet`.
* **Reality Mode**: plan↔reality overlays and visual diagnostics (Slice B style).

## 2) The WYSIWYG editor (Document Mode)

### 2.1 Document model (implementable contract)
The “Living Document” is an **authored artefact**, distinct from ingested evidence documents.
Canonical storage shape: `schemas/AuthoredArtefact.schema.json`.

Minimum requirements:
* block/heading/paragraph/list/table support
* inline **citations** that bind text spans to `EvidenceRef[]`
* embedded **EvidenceCards** (block embeds) that render provenance + limitations
* a “suggestion layer” that can be accepted/rejected without corrupting the base document

### 2.2 AI assistance UX (no black-box writing)
AI assistance is delivered as **structured suggestions**, not silent edits:
* **Ghost text**: inline grey suggestion at cursor/selection.
* **Comment bubbles**: margin comments with proposed rewording + evidence bindings.
* **Gold underlines (reasoning gaps)**: a “Review” pass that flags uncited claims, missing evidence, or missing statutory tests (powered by the governance linter + agents).

Every accept/reject action creates an `AuditEvent` (who accepted what suggestion, when, in which artefact).

### 2.4 “Get a draft” (draft-anything launcher)
Planners need a fast first draft of *anything* — not as a final output, but as an editable starting point.

UI requirement:
* A persistent **Draft** action (button + command palette) available in Document, Map, and Judgement modes.

Draft action contract:
* Input: a `DraftRequest` (`schemas/DraftRequest.schema.json`) including time budget (e.g. 10–30 seconds).
* Output: a `DraftPack` (`schemas/DraftPack.schema.json`) containing structured `DraftBlockSuggestion[]` suitable for ghost text/comment bubbles.
* Rule: draft suggestions must be traceable (each suggestion carries `EvidenceRef[]` and/or explicit assumptions); acceptance is always an `AuditEvent`.
* Rule: if a suggestion implies a recommendation/position, it must be marked `requires_judgement_run = true` and linked to (or trigger) a full grammar run before sign-off.

### 2.3 Insert-by-evidence (drag/drop)
Users can drag an `EvidenceCard` from the shelf into the document to:
* insert a citation mark, or
* embed the full card (for appendices / evidence schedules).

This is the “planner-shaped” interaction that makes provenance usable.

## 3) Judgement Mode (Scenario × Political Framing tabs)

### 3.1 Tab semantics
* A **tab** is a `ScenarioFramingTab` with its own `run_id` and outputs (`Trajectory` + `ScenarioJudgementSheet`).
* Tabs are generated from a `ScenarioSet` (`schemas/ScenarioSet.schema.json`).

### 3.2 Sheet semantics
* Sheets are produced from structured objects and deterministically rendered (`render/HTML_COMPOSER_SPEC.md`).
* The UI must support “inspect evidence” interactions:
  * click an evidence card → show supporting `EvidenceRef` fragments + tool runs + limitations.

### 3.3 Comparison UX (no cockpit)
Comparison is tab switching plus a small set of purpose-built comparison views:
* **Scenario delta** panel (`schemas/ScenarioDelta.schema.json`): what changed and why it matters.
* **Matrix views** (optional in v1, required in v2):
  * conflict matrix (policy/constraint conflicts by scenario)
  * opportunity matrix (benefit signatures by scenario)
  * similarity heatmap (scenario distance in policy/spatial space)

## 4) Map Mode (spatial reasoning surface)
See also: `ux/VISUOSPATIAL_WORKBENCH_SPEC.md` (Map/Plan/Photomontage canvases).

### 4.1 Core interactions
* draw marker/lasso → create a query context (geometry) for tools and agents
* toggle layers (“themes”), including scenario overlays and constraint layers
* one-click “snapshot to document” (map view becomes an artefact and an EvidenceCard)

### 4.2 Rendering contract
Maps may be interactive, but any artefact used for judgement must be storable and citeable:
* map screenshots, overlays, and exported tiles must be stored as artefacts and referenced by `EvidenceRef`.

## 5) Infographics & figures (charts, tables, extracted images)

### 5.1 Deterministic rendering spine
* Build `FactTable` objects with per-cell provenance (`render/FACT_TABLE_SPEC.md`).
* Agents propose `FigureSpec` objects referencing FactTable fields (`schemas/FIGURE_SPEC.schema.json`).
* Renderers produce SVG/PNG/HTML artefacts used in sheets and documents.

### 5.2 Figure Workbench (UI)
The UI must allow:
* preview a proposed figure
* inspect underlying FactTable + provenance
* accept → saves artefact and exposes it as an EvidenceCard for insertion

### 5.3 Extracted images
Ingested `visual_assets` (plans, diagrams, figures) must be viewable as evidence:
* page location, source document, and any VLM interpretations are surfaced with limitations.

## 6) UI build strategy (vertical slices)
UI work must ship as **vertical slices** that prove value end-to-end, not as a long “frontend-only” branch.

Recommended UI slice order (Spatial Strategy first):
1. **Timeline + stage gating** (Strategic Home) reading `culp/PROCESS_MODEL.yaml` artefacts/status.
2. **Document Mode editor v0** (basic editing + citations + evidence shelf).
3. **Judgement Mode viewer v0** (Scenario × Framing tabs + rendered sheet + evidence drill-down).
4. **Map Mode v0** (draw-to-ask + layer toggles + snapshot to EvidenceCard).
5. **Trace Canvas v0** (flowchart trace + “why chain” highlighting).
6. **Draft launcher v0** (DraftRequest → DraftPack suggestions + audit accept/reject).
7. **Ghost text + suggestions** (structured suggestions + audit events).
8. **Figure Workbench v0** (preview + provenance + insert).

DM and Monitoring surfaces follow after Spatial Strategy proves the spine.
