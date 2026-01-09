# CULP Monitoring & Governance — UI Behaviour Spec (#5)
> v1 target: implementable in `demo_ui` and verifiable via screenshots (Given/When/Then).

## 0) Purpose (planner framing)
Monitoring is not “analytics”. It is the **statutory governance loop** that maintains plan soundness over time:
- evidence currency
- delivery trajectories
- gateway readiness
- contested items that must be resolved (or explicitly positioned)

This spec defines monitoring as **workflows** that route back to the drafted plan state.

## 1) Monitoring signals (v1)
Signals appear in the `Monitoring` surface as a list/table of items with:
- Severity: `Settled / Provisional / Review` (no red=“against” semantics)
- Trigger type: `currency` / `divergence` / `gateway` / `contested`
- Scope: affected allocations/policies/evidence (count badges)

## 2) Remediation actions (v1)
Every monitoring signal must have at least one visible remediation action:
- `Create evidence task` (v1: toast + feed item)
- `Trigger scenario rerun` (v1: toast; opens Scenarios surface)
- `Flag policy review` (v1: toast; opens Policy sidebar)
- `Create gateway snapshot` (v1: toast; opens Trace Overlay with run target)

## 3) Tie-back rules (v1)
Monitoring never lives “over there”. Clicking a signal must route back to affected plan artefacts:
- If spatial: highlight affected sites on the map (or open Map panel)
- If textual: open Deliverable and scroll to relevant section (v1: optional; can be a toast + highlight)
- If evidential: open Evidence sidebar filtered to relevant items

## 4) Acceptance tests (Given/When/Then)

### Scenario: Monitoring is a governance workspace
Given I open the `Monitoring` surface
Then I see a set of plan soundness signals (evidence gaps, gateway readiness, trajectories)
And each has an explicit status and provenance posture

### Scenario: A signal routes back to the plan state
Given a monitoring signal references `Transport baseline`
When I click the signal (or its “Review” control)
Then the UI opens the relevant surface (Deliverable / Map / Evidence)
And a highlight/trace indicates what is affected

### Scenario: Gateway readiness produces a snapshot action
Given a monitoring signal is of type `gateway`
When I click `Create gateway snapshot`
Then a toast confirms the snapshot
And Trace Overlay can be opened for the run snapshot

