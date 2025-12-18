# UI System Specification (Planner Workbench / Digital Case Officer)

This document makes the UI implementable without weakening the “grammar-first, provenance-first” architecture.

The core UI idea is planner-native:
* planners work a **file** (deliverable) through a **process** (CULP plan-making or DM casework),
* AI behaves like a careful colleague (suggests/drafts/checks), and
* defensibility is experienced through **graphical traceability** (Trace Canvas), not JSON logs.

For planner-first workflow intent, see `ux/PLANNER_WORKFLOWS_SPEC.md`.
For the information architecture, see `ux/DASHBOARD_IA.md`.

## 0) Two top-level workspaces (the “two modes” requirement)
The product has two primary workspaces, each with process-native navigation and default objects:

1. **Local Plan / Spatial Strategy workspace**
   - Home: **Strategic Home** (CULP programme board + stage gates).
   - Primary objects: `PlanProject`, CULP artefacts, scenarios, sites, policies, consultation corpora.
   - Primary comparison surface: **Scenario × Political Framing** tabs (Judgement view).

2. **Development Management (DM) workspace**
   - Home: **Casework Home** (inbox + statutory deadlines + negotiation thread).
   - Primary objects: `Application`, revisions, consultees, conditions, decisions.
   - Comparison surface: revision deltas + (optionally) position packages under explicit framings.

Both workspaces reuse the same Workbench Shell; they differ in the left rail and default context anchors.

Naming note:
* The **mode names** shown in the UI are product copy and can be refined without changing the architecture.
* The requirement is the existence of two distinct workspaces: plan-making (CULP) and DM casework.

View naming note (B1):
* The workbench keeps four stable views (Document / Map+Plan / Judgement / Reality).
* Labels should be workspace-aware (e.g. Plan: “Scenarios”, DM: “Officer Report”) while keeping the same underlying view model.

## 1) UI invariants (non-negotiable)
1. **Dashboard is canonical UI**: all work happens in the workbench (`ux/DASHBOARD_IA.md`).
2. **Grammar-first judgement**: any judgement output is produced via the 8 moves (`grammar/GRAMMAR.md`) and logged (`schemas/MoveEvent.schema.json`).
3. **Non-deterministic agents are allowed**: replayability is via stored artefacts + deterministic rendering, not deterministic prose (`tests/REPLAYABILITY_SPEC.md`).
4. **Provenance everywhere**: any claim/suggestion/figure must trace to `EvidenceRef` and/or `ToolRun` (`db/PROVENANCE_STANDARD.md`).
5. **User is the selector**: tab selection, accept/reject, and sign-off are explicit `AuditEvent`s (`schemas/AuditEvent.schema.json`).
6. **Explainability modes**: `summary` / `inspect` / `forensic` are UI projections over the same run data.
7. **Visuospatial reasoning is first-class**: maps, plans, photos, and photomontages are core evidence surfaces (`ux/VISUOSPATIAL_WORKBENCH_SPEC.md`).
8. **Snapshots support legal questions**: published/sign-off states link to “what was known when” (`schemas/Snapshot.schema.json`).

## 2) Workbench Shell (v1)
The Workbench Shell is one consistent layout shared across both workspaces.

### 2.1 Header (process-aware)
Required elements:
* Mode switch: `Plan Studio` ↔ `Casework`
* Breadcrumbs: `Projects > {authority} > {stage/case} > {deliverable}`
* Stage/deadline indicator:
  - CULP: stage gate status
  - DM: statutory clock
* Audit ribbon (trust surface; see below)
* Primary actions: `Draft` · `Insert evidence` · `Review` · `Export`

### 2.2 Left rail (process-native)
The left rail answers “what file am I working and what’s next?”.

* Local Plan: programme board / stage list / critical path / required artefacts
* DM: inbox / case list / negotiation & consultation thread / key dates

### 2.3 Main pane (views over the active file)
The active deliverable is shown in one of these views:
* **Document view (default)**: Living Document (WYSIWYG deliverable)
* **Map/Plan view**: Map Canvas + Plan Canvas, exporting citeable artefacts
* **Judgement view**: Scenario × Political Framing tabs + rendered sheets
* **Reality view**: photomontage/site photo evidence + caveated interpretations

### 2.4 Context margin (30%)
The right margin makes “AI assistance” usable without becoming unaccountable:
* Smart Feed (cursor/selection-aware)
* Live Policy Surface (policy chips + explainable relevance)
* Evidence Shelf (draggable `EvidenceCard`s)
* Mini map / visual preview (expand into canvases)

### 2.5 Audit ribbon (cross-cutting trust surface)
Required ribbon elements:
* active `run_id` and (when used) active `snapshot_id`
* governance flags count + quick drill-down
* one-click export controls (evidence bundle + trace graph)
* explainability mode toggle (`summary` / `inspect` / `forensic`)

### 2.6 Trace Canvas (graphical traceability overlay)
Traceability must be experienced as a flowchart (not JSON):
* Spec: `ux/TRACE_CANVAS_SPEC.md`
* Data: `schemas/TraceGraph.schema.json` (derived deterministically from `MoveEvent` + `ToolRun` + `AuditEvent`)

UI rule:
* “Why is this here?” on any sentence/figure/policy chip opens Trace Canvas focused on upstream nodes.

### 2.7 “Get a draft” (draft-anything launcher)
Planners need a fast first draft of anything, then the tooling to make it defensible.

UI requirement:
* persistent `Draft` action (button + command palette) available in all views

Contract:
* Input: `DraftRequest` (`schemas/DraftRequest.schema.json`) with a time budget
* Output: `DraftPack` (`schemas/DraftPack.schema.json`) with `DraftBlockSuggestion[]`
* Suggestions are structured and traceable; accept/reject always creates an `AuditEvent`
* Any suggestion implying a position must link to (or trigger) a full grammar run before sign-off

### 2.7.1 Preflight (A3: preflight + action-first)
To achieve a “frontier AI workbench” feel without losing contestability, the UI supports **preflight**:
background, time-bounded preparation work triggered by navigation (open stage/tab/case).

Spec: `ux/PREFLIGHT_SPEC.md`

### 2.8 Insert-by-evidence (drag/drop)
Users can drag an `EvidenceCard` into the document to:
* insert a citation mark, or
* embed the full card (appendices / evidence schedules)

This is the planner-native bridge between evidence and writing.

## 3) Home screens (v1)

### 3.1 Strategic Home (CULP programme board)
Purpose: keep the system aligned to the GOV.UK 30‑month process (`culp/PROCESS_MODEL.yaml`).

Required elements:
* timeline/dependency chart (stages, blockers, status)
* stage gate panel (required artefacts and what’s missing)
  - required artefacts: `culp/PROCESS_MODEL.yaml` + `culp/ARTEFACT_REGISTRY.yaml`
  - per-project status: `CulpArtefactRecord` (`schemas/CulpArtefactRecord.schema.json`)
* quick link from any published artefact → the snapshot/run set used for sign-off

### 3.2 Casework Home (DM inbox)
Purpose: manage real workloads and deadlines without losing the reasoning thread.

Required elements:
* inbox board (new/validating/consultation/assessment/determination/issued)
* statutory deadline visibility + simple filters
* one-click open into the Application Workspace (same shell)

## 4) Judgement view (Scenario × Political Framing tabs)

### 4.1 Tab semantics
* tab is a `ScenarioFramingTab` with its own `run_id` and outputs (`Trajectory` + `ScenarioJudgementSheet`)
* tabs are generated from a `ScenarioSet` (`schemas/ScenarioSet.schema.json`)

Planner semantics:
* Plan-making: “strategy option S under framing F”
* DM: “position package P under framing F”

### 4.2 Sheet semantics
* sheets are deterministically rendered from stored structured objects (`render/HTML_COMPOSER_SPEC.md`)
* evidence drill-down must expose `EvidenceRef` fragments + tool runs + limitations

### 4.3 Comparison UX (no cockpit)
Comparison is tab switching plus purpose-built deltas:
* `ScenarioDelta` (“what changed, why it matters”) (`schemas/ScenarioDelta.schema.json`)
* optional matrices (conflict/opportunity/similarity) as later capability cards

## 5) Map/Plan/Reality views (visuospatial reasoning)
See also: `ux/VISUOSPATIAL_WORKBENCH_SPEC.md`.

Core interactions:
* draw marker/lasso → create a query context
* toggle layers (constraints, scenarios, evidence overlays)
* one-click “snapshot to document” (exports `ProjectionArtifact` + `EvidenceCard`)
* registration/overlay workflows must show uncertainty and limitations

## 6) Infographics & figures (charts, tables, extracted images)
Rendering spine:
* build `FactTable` objects with per-cell provenance (`render/FACT_TABLE_SPEC.md`)
* agents propose `FigureSpec` referencing FactTable fields (`schemas/FIGURE_SPEC.schema.json`)
* renderers produce SVG/PNG/HTML artefacts for sheets and documents

UI requirement:
* Figure Workbench supports preview → inspect provenance → accept → insert as EvidenceCard

## 6.1 WYSIWYG editor technology choice (E2)
The Living Document must be a real rich editor (not a textarea).

Chosen approach:
* **TipTap / ProseMirror** rich text editor
* document stored as ProseMirror JSON in `AuthoredArtefact.content`
* graphics are embedded as block nodes that reference stored artefacts (SVG/PNG/GeoJSON) rather than inlining raw binaries

Graphics support (minimum):
* images (evidence photos, extracted plan snippets)
* figures/charts (rendered outputs from `FigureSpec` + FactTables)
* tables (editable, citeable where possible)
* map snapshots (static) inserted from Map Canvas


## 7) UI build strategy (vertical slices)
Ship UI as vertical slices that prove end-to-end value (Spatial Strategy first):
1. Strategic Home v0 (timeline + stage gating)
2. Document view v0 (basic editing + citations + evidence shelf)
3. Judgement view v0 (Scenario × Framing tabs + sheet viewer)
4. Map/Plan view v0 (draw-to-ask + snapshot-to-evidence)
5. Trace Canvas v0 (flowchart + “why chain” highlight)
6. Draft launcher v0 (DraftRequest → DraftPack + accept/reject audit)
7. Suggestions UX v0 (ghost text + comment bubbles + governance underlines)
8. Figure Workbench v0 (preview + provenance + insert)

DM and Monitoring build once the Spatial Strategy spine is proven.
