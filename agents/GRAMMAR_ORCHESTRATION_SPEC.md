# Grammar Orchestration Specification

This spec describes the **Agentic / LLM Conductor** for the frozen 8‑move grammar (`grammar/GRAMMAR.md`).
It is the orchestration substrate that:
* coordinates specialist agents,
* builds retrieval frames and context packs,
* calls tools/instruments,
* emits structured move outputs,
* and produces a traceability procedure log.

## 1) Execution model (workflow-driven)
The orchestrator runs as a `WorkflowProvider` workflow (LangGraph in OSS, Microsoft Agent Framework in Azure).

**Unit of execution (Spatial Strategy)**
* The primary unit is a **Scenario × Political Framing tab** (`ScenarioFramingTab`).
* Each tab run produces one full 8-move trace and one `Trajectory` + `ScenarioJudgementSheet`.

**Batch execution**
* Scenario generation produces a `ScenarioSet` and then schedules tab runs (parallel where safe).
* Tab selection is always a human action recorded as an `AuditEvent`.

## 2) The 8-move loop (with explicit backtracking)
The orchestrator must run the 8 moves in sequence.
Backtracking is allowed but must be explicit (a new `MoveEvent` that records the reason for returning to an earlier move).

## 3) Non-determinism + traceability
LLM/VLM providers are allowed to be non-deterministic.
Traceability is guaranteed by persisting:
* every move’s structured outputs (`MoveEvent.outputs`)
* every tool/model call (`ToolRun`)
* context bundle references for judgement outputs

## 4) Agent roles (specialists, not one mega-agent)
Minimum roles (shared across pipelines):
* **Scout**: builds retrieval frames; expands KG; curates evidence candidates.
* **Analyst**: produces `Interpretation[]` and `ReasoningTrace[]`; requests missing instruments.
* **Judge**: produces `WeighingRecord`; makes trade-offs explicit under framing.
* **Scribe**: drafts `Trajectory` and sheet narratives (always conditional on framing).

Spatial Strategy adds (at least):
* **Scenario Builder**: turns natural language prompts into `ScenarioStateVector` objects.
* **Scenario Delta Interpreter**: produces `ScenarioDelta` objects (what changed and why it matters).

## 5) Prompt library + versioning (audit requirement)
Every LLM/VLM call must reference a `prompt_id` + `prompt_version` (see `platform/PROVIDER_INTERFACES.md`).
Prompt changes are treated as first-class governance events (diffable, reviewable).

## 5.1 Drafting workflows (fast first drafts)
“Get a draft” actions in the UI are implemented as time-budgeted drafting workflows that produce structured suggestion packs, not silent edits.
* Spec: `agents/DRAFT_LAUNCHER_SPEC.md`

## 6) Tool calling (no rummaging, typed tools)
Agents do NOT hallucinate data. They CALL tools:
* `get_policy_stack(...)`
* `get_site_fingerprint(...)`
* `get_visual_evidence(...)`

Tool calls must be logged as `ToolRun` and referenced from `MoveEvent.tool_runs`.

Context Assembly note:
* Retrieval is necessary but insufficient for visuospatial judgement and tool planning.
* Context Assembly builds **multimodal, budgeted context packs** from hybrid retrieval + KG expansion (spec: `agents/CONTEXT_ASSEMBLY_SPEC.md`).

## 7) Predictable degradation
If a tool/model is unavailable, the orchestrator may:
* fall back to safe heuristics (marked `fallback_mode = true`), or
* stop and raise a blocking `ToolRequest` for human resolution.

Fallback output must be explicitly caveated via `limitations_text` and governance warnings.
