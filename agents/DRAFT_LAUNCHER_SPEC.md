# Draft Launcher (Get-a-Draft-for-Anything) Specification

Planners often need a usable first draft in minutes (or seconds): after a meeting, before a committee deadline, or to start an evidence schedule.

This spec defines a **Draft Launcher** workflow that produces a fast, editable draft while preserving the system’s procedural explainability.

## 1) What “Get a draft” means (and what it does NOT mean)
* A draft is **suggested content**, not a determination and not an automatic edit.
* Drafts are delivered as structured suggestions (`DraftPack`) suitable for ghost text/comment bubbles in the Living Document.
* If a draft implies a recommendation/position, it must be marked `requires_judgement_run = true` and linked to (or trigger) a full grammar run before sign-off.

## 2) Inputs/outputs
**Input**: `DraftRequest` (`schemas/DraftRequest.schema.json`)

**Output**: `DraftPack` (`schemas/DraftPack.schema.json`)
* `status = partial` is allowed when time-bounded or evidence-limited (must include limitations).

## 3) Execution pattern (time-budgeted, tool-first)
The workflow is time-budgeted (e.g. 10–30 seconds) and runs in three phases:

1. **Frame** (fast)
   - Convert user intent + context into retrieval frames (topic, authority/stage/app, geometry filters).
   - Decide which existing artefacts to reuse (prior drafts, prior runs, prior evidence cards).

2. **Gather** (bounded)
   - Call retrieval + graph expansion tools to gather candidate evidence atoms/cards.
   - If evidence is missing, create explicit “data-gap” assumptions rather than inventing facts.

3. **Compose** (structured)
   - Call the LLM in **structured mode** to produce `DraftBlockSuggestion[]`.
   - Each suggestion must carry `evidence_refs[]` (empty is allowed only for non-factual boilerplate such as headings).

All phases must emit `ToolRun` logs (retrieval, spatial ops, model calls).

## 4) Background completion (optional)
After a quick draft is produced, the system may schedule deeper work asynchronously:
* run the full 8-move grammar for Scenario × Framing tabs
* generate figures (FactTables + FigureSpecs) and attach as insertable evidence cards
* run additional instruments (flood, connectivity, SEA/HRA checks)

The UI must show these as “pending” and allow the planner to decide what to accept.

## 5) Governance hooks
The Draft Launcher must integrate with:
* prompt library/versioning (`agents/PROMPT_LIBRARY_SPEC.md`)
* audit events for accept/reject/insert actions (`schemas/AuditEvent.schema.json`)
* reasonableness linter warnings for uncited factual suggestions (future rule; see `governance/REASONABLENESS_LINTER_SPEC.md`)

