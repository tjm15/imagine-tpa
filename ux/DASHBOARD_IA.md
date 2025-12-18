# Dashboard Information Architecture (Planner Workbench / Digital Case Officer)

## Core Principle: planners work the file through a process
The dashboard is not “multiple apps” (maps app, judgement app, trace app). It is one **planning file workspace** that:
* keeps the **deliverable** (plan chapter / site assessment / officer report / decision notice) central at all times, and
* adapts navigation to the **process** the planner is actually in (CULP plan-making vs DM casework).

The “surfaces” are **views of the same file**, not separate destinations.

See also:
* `ux/PLANNER_WORKFLOWS_SPEC.md` (planner-native jobs-to-be-done)
* `ux/UI_SYSTEM_SPEC.md` (implementable UI contracts)

## Two primary workspaces (the “two modes” requirement)
1. **Local Plan / Spatial Strategy workspace (CULP-native)**
   * Home: **Strategic Home** (30-month programme board + stage gates)
   * Primary objects: `PlanProject`, CULP artefacts, scenarios, sites, policies, consultation corpora
2. **Development Management workspace (casework-native)**
   * Home: **Casework Home** (inbox + statutory deadlines + negotiation/revision tracking)
   * Primary objects: `Application`, revisions, consultation responses, conditions, decisions

Both workspaces reuse the same Workbench Shell (below), but their “left rail” and defaults are different.

Naming note:
* Workspace names shown in the header are product copy; the architectural requirement is that both workspaces exist and remain distinct.
* Current UI labels: **Plan Studio** (plan-making/CULP) ↔ **Casework** (DM).

## Mode + view naming (B1: keep the views, change the language)
The four views are a stable workbench mental model (“same file, different lens”), but the labels should be planner-native and mode-aware.

Recommended label mapping (copy-only; does not change the underlying architecture):
* **Plan-making workspace**
  - Document view → **Deliverable**
  - Map/Plan view → **Map & plans**
  - Judgement view → **Scenarios**
  - Reality view → **Visuals**
* **DM workspace**
  - Document view → **Officer Report**
  - Map/Plan view → **Site & Plans**
  - Judgement view → **Balance**
  - Reality view → **Photos**

These names can be refined (including the mode switch labels) without changing the workbench kernel.

## Capability Navigation (Reasoning Chain)
The dashboard exposes capability modules through a planner-friendly chain:
`Evidence → Context → Patterns → Options → Tests → Judgement → Explanation`.

This is **UI navigation**, not the judgement engine. Judgement is still produced via the frozen 8-move grammar (`grammar/GRAMMAR.md`) and logged as `MoveEvent`s (`schemas/MoveEvent.schema.json`).

## Workbench Shell (planner-native mental model)

### 1) Header (minimal, process-aware)
Always visible:
* **Mode switch**: `Plan Studio` ↔ `Casework`
* **Breadcrumbs**: `Projects > {authority} > {stage/case} > {deliverable}`
* **Stage / deadline indicator**:
  - CULP: current stage and gate status (“Blocked”, “In progress”, “Ready to publish”)
  - DM: statutory clock (“X days remaining”, “Overdue”)
* **Audit ribbon** (trust surface): active run/snapshot, governance flags, export bundle (see `ux/UI_SYSTEM_SPEC.md`)
* **Primary actions**: `Draft` · `Insert evidence` · `Review` (governance) · `Export`

“Frontier AI” feel (without losing defensibility) is achieved via **preflight**:
* opening a stage/tab/case triggers time-bounded background preparation work
* outputs are proposals (draft packs, evidence cards, tool requests), not silent edits
* spec: `ux/PREFLIGHT_SPEC.md`

### 2) Layout (70/30, plus a left rail)
Planners need a stable “Word-like” centre with context in the margin.

* **Left rail (process rail)**: “what file am I working and what’s next?”
  - CULP: programme board / stage list / critical path / required artefacts
  - DM: inbox / case list / consultation timeline / negotiation log
* **Main workspace (70%)**: the active deliverable in one of the views below
* **Context margin (30%)**: evidence + policy + “why” interactions (see below)

### 3) Views (same file, different lenses)
The views are toggles on the active file, not separate apps:
* **Document view (default)**: the Living Document (WYSIWYG deliverable)
* **Map/Plan view**: Map Canvas + Plan Canvas (draw-to-ask, overlay-to-cite)
* **Judgement view**: tabbed sheets for Scenario × Political Framing combinations
* **Reality view**: photomontage / site photo reasoning (where available)

Traceability is not a “view” you go away to read; it is a **Proof overlay**:
* **Trace Canvas overlay**: flowchart derived from `MoveEvent`/`ToolRun`/`AuditEvent` (`ux/TRACE_CANVAS_SPEC.md`)

## Context margin (what makes it planner-grade)
The right margin is where “AI assistance” becomes usable without becoming unaccountable:
* **Smart Feed**: context-aware cards based on cursor/selection/site/scenario
* **Live Policy Surface**: policy chips with explainable relevance badges (“why is this here?”)
* **Evidence Shelf**: draggable, citeable `EvidenceCard`s (`schemas/EvidenceCard.schema.json`)
* **Mini map / visual preview**: “what is here?” snapshot, expandable into canvases

## Strategic Home (CULP) — programme board not a dashboard
Purpose: “what will block us and what must be produced next?”
* **Dependency / critical path chart** across the GOV.UK 30‑month process (`culp/PROCESS_MODEL.yaml`)
* **Stage gate panel** showing required artefacts and their status:
  - required artefacts: `culp/PROCESS_MODEL.yaml` + `culp/ARTEFACT_REGISTRY.yaml`
  - per-project status: `CulpArtefactRecord` (`schemas/CulpArtefactRecord.schema.json`)
* **Action list**: next steps derived from blockers (“commission transport evidence”, “complete SEA screening”)

## Casework Home (DM) — case file workflow, not a CRM
Purpose: “move cases through validation/consultation/determination with a defensible file”.
* **Inbox board** (Outlook-style): `New` / `Validating` / `Consultation` / `Assessment` / `Determination` / `Issued`
* **Deadline visibility**: days remaining, breached flags
* **Negotiation / revision thread**: what changed, why it matters (deltas are first-class)

## Scenario × Political Framing tabs (planner semantics in both modes)
Tabs are always **explicitly selected by the user** (audited), never silently chosen by an agent.

* **Plan-making**: tabs represent “strategy option S under framing F”
  - reasonable alternatives, site/transport/constraints implications, trade-offs
* **DM**: tabs represent “position package P under framing F”
  - approve/refuse/conditions/mitigation variants, with explicit assumptions and uncertainties

In both cases, each tab has its own run log and sheet:
* `ScenarioFramingTab` → `Trajectory` + `ScenarioJudgementSheet`

## Interaction rules (planner-shaped)
* **Draft-first, then defend**: “Get a draft” is always available, then governance/trace makes it safe.
* **Draw to ask**: in Map/Plan views, drawing triggers a query context.
* **Snapshot to cite**: any map/overlay can be exported into the deliverable as citeable evidence.
* **Why is this here?**: any sentence/figure/policy chip can reveal upstream evidence/tests via Trace Canvas.
* **Accept/reject is explicit**: AI suggests; the user commits; actions are logged (`AuditEvent`).

## Mobile / site visits
The same shell must degrade gracefully to tablet use:
* Map/Reality views become primary during site visits
* Evidence cards and snapshots remain one-tap insertable into the file
