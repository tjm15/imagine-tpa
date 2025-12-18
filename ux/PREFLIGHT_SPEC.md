# Preflight Specification (A3: preflight + action-first)

This spec pins down design choice **A3 — Preflight + action-first assistance**:
TPA behaves like a planning workbench that is already “getting things ready” as the planner navigates, while keeping every suggestion contestable and auditable.

Preflight is the difference between:
* “click Draft and wait”, and
* “open a stage/case and the system has already assembled the likely next moves”.

## 0) What preflight is (and is not)

Preflight IS:
* background, time-bounded preparation work triggered by navigation/context changes
* creation of **proposal objects** (draft packs, tool requests, evidence cards), never silent edits
* a way to keep the UI feeling “frontier AI” without becoming a chatbot

Preflight IS NOT:
* a judgement run (unless explicitly requested)
* automatic publishing, sign-off, or determination

## 1) Triggers (planner actions)

Preflight triggers are explicit `AuditEvent`s and should be cheap to run repeatedly:
* open a `PlanProject` stage (CULP)
* open a `ScenarioFramingTab`
* switch into Map/Plan/Reality view
* select a site / draw a geometry
* open a DM case (application)

## 2) Outputs (proposal-first)

Preflight produces *proposals* that the planner can accept/reject:
* `DraftPack` suggestions (fast first drafts; `agents/DRAFT_LAUNCHER_SPEC.md`)
* `ToolRequest[]` when evidence gaps are detected (`schemas/ToolRequest.schema.json`)
* “Evidence Shelf” recommendations (candidate `EvidenceCard`s; `schemas/EvidenceCard.schema.json`)
* “Next actions” recommendations (UI-only, but linkable to the underlying tool runs)

All provider/tool calls must still emit `ToolRun` logs (`schemas/ToolRun.schema.json`).

## 3) Interaction model (UI)

Preflight must feel like an IDE:
* a visible “Prepared” state (“Prepared 2m ago”, “Updated after map change”)
* streaming progress into the Smart Feed (“retrieving policies…”, “rendering map snapshot…”)
* proposals appear as cards with accept/reject

UI rule:
* accepting any suggestion creates an `AuditEvent` (who accepted what, when).

## 4) Budgets and escalation

Preflight runs under strict budgets (time and tool cost):
* initial preflight: 5–15s budget
* follow-up deeper jobs: queued and shown as pending (“working…”) rather than blocking the UI

If preflight work would materially change a judgement position, it must:
* either link to an existing judgement run, or
* schedule a full 8-move run and mark the proposal `requires_judgement_run = true`.

## 5) Implementation spine

Preflight is implemented as a `WorkflowProvider` workflow:
* OSS: LangGraph
* Azure: Microsoft Agent Framework lineage

The workflow runs over typed tools (no “LLM rummaging”) and produces proposal objects.

