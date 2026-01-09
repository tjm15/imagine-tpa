# Modes as Choreography — UI Behaviour Spec (#3)
> v1 target: implementable in `demo_ui` and verifiable via screenshots (Given/When/Then).

## 0) Purpose (planner framing)
Scrutiny modes are **views onto the same reasoning substrate**, not different exports.

In v1, choreography is expressed through:
- **Surfaces** (Overview / Deliverable / Map & Plans / Scenarios / Visuals / Monitoring)
- **Detail mode** (Summary / Inspect / Forensic)
- **Drafting phase** (Controlled / Free drafting) for AI co‑drafting actions

This spec defines what is visible, what is actionable, and what becomes read‑only.

## 1) Surface choreography (v1)

### 1.1 Overview (CULP cockpit)
**Visible**
- Stage spine + programme progress
- Checklist + required artefacts
- Stage warnings (summarised)
- Co‑drafter callout

**Actionability**
- Navigation is allowed (open deliverable/map/scenarios)
- Apply patch bundles is **disabled** from Overview (read-only posture)

### 1.2 Deliverable (Drafting surface)
**Visible**
- Deliverable header (status + provenance)
- Editor (HTML-native)
- Inline AI review hints (counts + severity)

**Actionability**
- Editing enabled
- Co‑drafter enabled (review + apply bundles)

### 1.3 Map & Plans (Drafting surface)
**Visible**
- Map canvas + stable layer toggles
- Candidate sites list

**Actionability**
- Select sites, toggle layers, export snapshot
- Co‑drafter bundle review can highlight sites

### 1.4 Scenarios
**Visible**
- Scenario × framing tabs
- Balance snapshot (headline only)

**Actionability**
- Switching scenarios is allowed
- Deep trace is routed to Trace Overlay (not inline)

### 1.5 Visuals
**Visible**
- Visual evidence blocks + overlays (v1 placeholders acceptable if labeled demo)

**Actionability**
- Trace access
- Export can exist but is not “the canonical pack”

### 1.6 Monitoring (CULP governance loop)
**Visible**
- Plan soundness monitoring signals
- Evidence gaps + gateway readiness indicators

**Actionability**
- Signals produce remediation actions (v1: toast + trace anchor)
- Monitoring links back to affected allocations/policies/evidence via highlight/trace

## 2) Detail mode choreography (Summary / Inspect / Forensic)

### 2.1 Summary (default)
- Minimal “why” content inline
- Hints show counts + short titles

### 2.2 Inspect
- Hints and sidebars reveal 1–3 lines of detail
- “Why?” affordances become visible without hover
- Trace Overlay opens in Inspect by default

### 2.3 Forensic
- Apply controls are disabled (read-only)
- Trace Overlay exposes tool runs, inputs/outputs, limitations

## 3) Drafting phase choreography (Controlled / Free drafting)
- Controlled: AI must propose; planner applies bundles explicitly.
- Free drafting: AI may auto‑apply bundles; every auto‑apply is logged and undoable.

## 4) Acceptance tests (Given/When/Then)

### Scenario: Overview is navigation-first, not apply-first
Given I am in `Overview`
When I open a patch bundle review
Then `Apply bundle` is disabled and marked read-only

### Scenario: Deliverable allows applying bundles in Summary mode
Given I am in `Deliverable`
And Detail mode is `Summary`
When I apply a patch bundle
Then the deliverable content changes visibly

### Scenario: Inspect/Forensic disables apply everywhere
Given I switch Detail mode to `Inspect` (or `Forensic`)
When I open a patch bundle review
Then `Apply bundle` is disabled
And Trace Overlay opens at the same detail level

### Scenario: Free drafting auto-apply is visible and reversible
Given Drafting phase is `Free drafting`
When a new patch bundle is requested
Then the bundle may auto-apply (demo)
And it appears in the Auto‑applied log with an `Undo` button

