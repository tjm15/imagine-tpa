# Plan Workspace & Artefacts — UI Behaviour Spec (#1)
> v1 target: implementable in `demo_ui` and verifiable via screenshots (Given/When/Then).

## 0) Purpose (planner framing)
The Plan workspace is a **living plan state**. The UI must make the manipulated artefacts explicit (and contestable) without collapsing into a document editor or a dashboard.

This spec defines the **on‑screen artefacts** planners handle and the **visible actions** available for each.

## 1) Artefact catalogue (UI model)
Each artefact has:
- **Card/panel form**: what it looks like in list/detail.
- **Actions**: visible controls a planner can take.
- **Map binding**: what happens on the map (highlight, focus, overlay).
- **UI IDs**: stable identifiers only where they appear in the UI (citations, deep-links, snapshots).

### 1.1 Deliverable (HTML‑native)
**Card/panel**
- Title + status badges (Draft / Provisional / Settled)
- Provenance/Why icon (opens Trace Overlay)

**Actions**
- Open in `Deliverable` surface
- Cite evidence by drag‑drop from Evidence sidebar
- Invoke Co‑drafter (opens Co‑drafter drawer)

**UI IDs**
- `deliverable_id` shown where cited (e.g., `deliverable-place-portrait` in Trace)

### 1.2 Allocation / Site
**Card/panel**
- Site name + capacity + site reference (e.g., `SHLAA/045`)
- Constraint flags (icons/badges)

**Actions**
- Select (cross‑highlights)
- Show on map (focus + outline)
- Trace (opens Trace Overlay anchored to the site)

**Map binding**
- Selecting a site highlights its polygon outline
- “Adjusted” boundaries render with a distinct outline (e.g., amber) to signal changed assumptions

**UI IDs**
- `site_id` is always visible in the UI where a site is referenced (`SHLAA/045`)

### 1.3 Policy (clause / card)
**Card/panel**
- Policy reference (e.g., `GB1`) + title
- Expandable body (in Policy sidebar)

**Actions**
- Expand/collapse
- Cite into deliverable
- Trace (Why icon)

**Map binding**
- If a policy has spatial scope, “Show scope” highlights its area layer (v1: optional; can be a map overlay)

**UI IDs**
- Policy reference is the stable ID used in the UI (e.g., `GB1`)

### 1.4 Evidence item
**Card/panel**
- Evidence title + type badge (Document / Map / Consultation / Photo)
- Draggable in Evidence sidebar

**Actions**
- Drag into deliverable to cite (creates citation mark)
- Open evidence detail modal (v1: modal)
- Trace (Why icon)

**Map binding**
- Evidence that is spatial (map/constraint) can toggle an overlay (v1: via Map/Constraints panels)

**UI IDs**
- Evidence ID used in citations (e.g., `ev-transport-dft`)

### 1.5 Issue (register item)
**Card/panel**
- Title + severity (Attention/Risk/Blocker semantics, not “for/against”)
- Status (Open / Provisional / Settled / Reverted)

**Actions**
- Open Trace (Why icon)
- Create remediation action (v1: toast + pinned feed item)

**Map binding**
- If spatially anchored, “Show on map” highlights affected sites/areas

**UI IDs**
- `issue_id` is visible in Trace and issue cards

### 1.6 Snapshot
**Card/panel**
- Snapshot name + timestamp + run id

**Actions**
- Export (HTML snapshot)
- Open Trace (links to run)

**Map binding**
- Snapshot can rehydrate map extent and overlay selection (v1: optional; visible via toast)

**UI IDs**
- `run_id` is always visible (e.g., `run_8a4f2e`)

### 1.7 Monitoring signal
**Card/panel**
- Signal title + trigger type (currency decay / divergence / gateway incompleteness)
- Severity + “Attention needed” badge

**Actions**
- Review (opens Monitoring view section)
- Remediate (creates task/issue; v1: toast)
- Trace (Why icon)

**Map binding**
- Clicking a signal focuses affected allocations (v1: highlight + open Map panel)

## 2) Acceptance tests (Given/When/Then)

### Scenario: Opening the Plan workspace lands on Overview cockpit
Given I open a Plan project
When the workspace loads
Then I see the `Overview` surface with a CULP stage spine and stage checklist

### Scenario: Evidence can be cited by drag‑drop
Given the right sidebar is set to `Evidence`
When I drag an Evidence card into the Deliverable editor
Then a citation is added and a toast confirms the citation

### Scenario: A site can be highlighted and traced
Given I am in `Map & Plans`
When I click a candidate site (e.g., `Northern Fringe`)
Then the site is visually highlighted on the map
And I can open Trace for the site

### Scenario: Artefact IDs are visible where they matter
Given I open Trace from a site or evidence item
Then the Trace header includes the artefact label and its stable UI identifier (site ref / evidence id / run id)

### Scenario: Co‑drafter bundles act on visible artefacts
Given a Patch Bundle exists in Co‑drafter
When I apply the bundle in a Drafting surface
Then I see a visible change in the Deliverable (text added/updated)
And I see a visible change on the map (highlight/adjusted outline) for any spatial item

