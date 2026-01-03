# AI Co‑Drafter Semantics — UI Behaviour Spec (#4)
> v1 target: implementable in `demo_ui` and verifiable via screenshots (Given/When/Then).

## 0) Purpose (planner framing)
The AI co‑drafter operates on a **living plan state** (policies, allocations, evidence, issues, monitoring signals) and produces **structural proposals**. Scrutiny modes (overview / drafting / inspection / forensic) are **views onto the same reasoning substrate**, not separate “packs”.

This spec defines **how AI proposes plan-state changes**, how planners review them, and how changes remain contestable and reversible without turning the UI into constant nagging.

## 1) Terms (UI objects, not DB)
- **Patch Bundle**: a named set of proposed changes (“patch items”) that together resolve a detected inconsistency/risk/opportunity.
  - UI identity: `bundle_id` (short, stable, shown in UI; deep-linkable).
- **Patch Item**: a single change within a bundle, typed by the artefact it touches (policy text, allocation geometry, issue register, evidence links, justification).
  - UI identity: `item_id` (shown in review UI for reference).
- **Drafting Phase** (UI state): `Free Drafting` vs `Controlled Drafting`.
  - `Free Drafting`: AI may auto‑apply patch bundles (always logged; always reversible).
  - `Controlled Drafting`: AI must propose; planner must apply explicitly.
- **Trace View**: overlay that answers “Why is this here?” for bundles/items (anchored to the bundle/item).

## 2) Non‑negotiable UX rules (v1)
1. **AI changes are object‑level** by default: AI proposes patch bundles affecting artefacts; it does not silently edit the plan.
2. **One primary apply action**: bundles apply via a single `Apply bundle` control, after review.
3. **Per‑diff inspection is always available** (even when applying all at once).
4. **Auto‑apply only in `Free Drafting`**, and must be visibly indicated, reversible, and attributable.
5. **Uncertainty is not constant UI noise**:
   - default surfaces show *counts + severity*,
   - details appear on demand (Inspect/Forensic or via Trace / Issue views).

## 3) Required UI surfaces

### 3.1 “Co‑Drafter” entry + status
**Where**: persistent button in the workbench header (icon + label).
**Shows**: a status pill with counts:
- `Proposals (n)` where `n` is number of unapplied bundles.
- Optional: `Auto‑applied (n)` when in `Free Drafting`.

**Actions**:
- Opens the **Co‑Drafter Drawer** (right-side drawer) without changing the main view.

### 3.2 Co‑Drafter Drawer (proposal inbox)
Contains three sections (collapsible):
1. **Proposed bundles** (default open)
2. **Applied this session**
3. **Auto‑applied log** (visible only if `Free Drafting` is enabled)

Each bundle appears as a **Bundle Card** with:
- Title (human-readable, planner phrasing)
- Badges: `severity` (e.g. Attention / Risk / Blocker), `confidence` (High/Med/Low), `phase` tag if auto‑applied
- Affected artefacts summary: e.g. `2 policies · 1 allocation · 1 issue`
- Controls: `Review` (primary), optional `Apply bundle` (only when applicable), `Why?` icon

Drawer global controls:
- Toggle: `Drafting phase: Free / Controlled` (explicit, sticky, visible).
- Filter chips: `Policies`, `Allocations`, `Evidence`, `Issues`, `Monitoring`.

### 3.3 Patch Bundle Review (modal or full-height overlay)
Invoked from any Bundle Card via `Review`.

Layout requirements (screenshot-testable):
- **Header**: Bundle title + `bundle_id` + badges + timestamp.
- **Bundle rationale** (2–4 lines max) with `Why?` icon (opens Trace View).
- **Patch item list** with per-item expand/collapse:
  - each item shows: type icon, `item_id`, affected artefact name, “before → after” summary line.
  - each item has a `Show on map` affordance if it touches geometry or spatial scope.
  - each item has an `Inspect diff` affordance.
- **Controls row**:
  - Primary: `Apply bundle` (enabled only in Drafting modes that allow it)
  - Secondary: `Apply in parts` (opens per-item selection)
  - Secondary: `Dismiss` (keeps bundle but closes review)

### 3.4 Diff inspectors (per item)
Each patch item type MUST render a concrete diff:

1) **Policy text diff**
- Side-by-side or inline diff with additions/removals highlighted.
- Shows policy reference and clause anchor.
- Buttons: `Open policy in main view`, `Why?` (Trace View).

2) **Allocation / site geometry diff**
- Map mini-preview with `Before` (outline) vs `After` (outline) and a `Fit to change` control.
- `Show on map` highlights the geometry in the main map (cross-highlighting).
- If the main view is not map, the map highlight still appears as an overlay outline (no forced navigation).

3) **Justification diff**
- Shows the justification section heading + redline diff.
- Provides `Link to affected policies/allocations` chips that cross-highlight.

4) **Evidence link updates**
- Shows evidence items added/removed as chips/cards (with provenance icon).
- Provides `Open evidence` and `Why?` controls.

5) **Issue register update**
- Shows issue created/updated/resolved with severity + status changes.
- Provides `Open issue` (focuses issue panel) and `Why?`.

## 4) Apply / undo / provenance (visible behaviours)

### 4.1 Applying a bundle (explicit)
Applying MUST:
- visibly update affected artefacts immediately (policy text, geometry, issue list, evidence links).
- add a visible entry in **Applied this session** (drawer section).
- add a visible “Applied by AI (accepted by {planner})” line in the bundle header history.
- expose a `Revert bundle` button for the most recently applied bundle (v1: last N bundles) in the review header and in Applied list.

### 4.2 Auto‑apply (Free Drafting only)
When `Free Drafting` is enabled:
- AI may apply bundles without a manual click.
- Every auto‑applied bundle MUST appear in **Auto‑applied log** with:
  - badge `Auto‑applied`
  - `Undo` button (one click)
  - `Review` button (shows diffs)
- The main workspace MUST show a transient toast: “AI applied: {bundle title} · Undo”.

### 4.3 Revert semantics (v1)
Reverting a bundle MUST:
- restore the previous visible state of all affected artefacts.
- mark the bundle card as `Reverted` (badge) in Applied/Auto‑applied lists.
- add a visible history line: “Reverted by {planner}”.

## 5) Mode choreography hooks (visibility + actionability)

### Overview mode
- Co‑Drafter Drawer is accessible.
- Bundles are visible, reviewable.
- `Apply bundle` is disabled (read-only) unless the planner explicitly enters a Drafting phase.

### Drafting mode
- `Controlled Drafting`: apply is allowed, auto‑apply is off.
- `Free Drafting`: auto‑apply is allowed, with the log + undo affordances.

### Inspection / Forensic modes
- Bundles/items are reviewable.
- Apply controls are disabled (read-only).
- Trace View opens in the current detail level:
  - Inspection opens to “inspect” detail by default.
  - Forensic opens to “forensic” detail by default.

## 6) Given/When/Then acceptance tests (screenshot-verifiable)

### Scenario: AI proposes a patch bundle (structural, not cursor-level)
Given I am in the Plan workspace with a plan open
When I click `Co‑Drafter` → `Request proposal`
Then a new Bundle Card appears under `Proposed bundles`
And the card shows a title, `bundle_id`, severity badge, confidence badge, and affected-artefacts counts
And the header status pill increments `Proposals (n)`

### Scenario: Reviewing a bundle shows per-item diffs
Given a Bundle Card exists in `Proposed bundles`
When I click `Review`
Then the Patch Bundle Review overlay opens
And I can expand each patch item to see a concrete diff (text diff or map preview)
And each item shows an `item_id` and an affected artefact name

### Scenario: Apply bundle updates multiple artefacts at once
Given I am in `Drafting: Controlled`
And a bundle contains a policy text diff and an allocation geometry diff
When I click `Apply bundle`
Then the policy text visibly changes in the deliverable/policy surface
And the allocation outline visibly updates on the map (or map overlay)
And the bundle moves to `Applied this session` with an `Applied` badge

### Scenario: Apply in parts allows selective application
Given I am reviewing a bundle with 4 patch items
When I click `Apply in parts`
Then a checklist appears beside each patch item
And I can apply a subset with `Apply selected`
And the bundle is marked `Partially applied` with “2/4 items applied”

### Scenario: Cross-highlighting from a geometry diff
Given I am reviewing an allocation geometry diff item
When I click `Show on map`
Then the main map highlights the affected geometry
And the review overlay indicates “Highlighted on map”

### Scenario: “Why?” opens Trace View anchored to the bundle
Given I am reviewing a bundle
When I click the bundle `Why?` icon
Then the Trace View opens
And it is labeled with the bundle title and `bundle_id`
And it highlights the upstream chain for this bundle (visible focus state)

### Scenario: Auto‑apply is only possible in Free Drafting and is undoable
Given I toggle `Drafting phase` to `Free Drafting`
When the system auto‑applies a bundle
Then a toast appears: “AI applied: {bundle title} · Undo”
And the bundle appears in `Auto‑applied log` with an `Undo` button
When I click `Undo`
Then the visible plan state reverts
And the bundle is marked `Reverted`

### Scenario: Inspection mode disables apply controls but keeps review
Given I switch to `Inspection` mode
When I open a Patch Bundle Review
Then `Apply bundle` is disabled and visually marked read-only
And I can still open diffs and Trace View

### Scenario: Uncertainty is available but not constantly nagging
Given a bundle has `confidence: Low`
When I view the bundle card in the drawer
Then I see a `Low` confidence badge
And I do not see inline warnings injected into the document by default
When I click `Why?`
Then the Trace View shows assumptions/limitations for the bundle (in Inspect/Forensic)

### Scenario: Bundle produces/updates an issue instead of spamming warnings
Given a bundle includes an `Issue register update` item
When I apply the bundle
Then an Issue chip/card appears in the Issues surface with the new severity/status
And the bundle card shows `1 issue` in its affected artefacts summary

## 7) Out of scope (v1)
- Multi-user merge/conflict resolution beyond “bundle superseded” badges.
- Automatic phase inference (“rules engine”); v1 uses an explicit Drafting phase toggle.
- Full plan-wide regeneration; v1 supports bundle proposals scoped to visible artefacts and selected context.
