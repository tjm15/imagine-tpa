# Prompt Library & Versioning Specification

The published reasoning architecture describes a **Prompt Library & Versioning** capability in the Agentic / LLM Conductor.

This repo treats prompt management as a **governance surface**, not an implementation detail.

## 1) Requirements
1. Every prompt has a stable `prompt_id` and monotonically increasing `prompt_version`.
2. Every LLM/VLM call must log `prompt_id` + `prompt_version` in its `ToolRun.outputs_logged` (`platform/PROVIDER_INTERFACES.md`).
3. Prompt updates must be reviewable and diffable (human-readable).
4. Prompt changes must be attributable (who/what changed it) and auditable (`AuditEvent`).

## 2) Storage model (profile-agnostic)
Store prompts in the canonical store (PostgreSQL via `CanonicalDBProvider`) so both Azure and OSS profiles behave identically.

Minimum fields per version:
* `prompt_id`
* `prompt_version`
* `name`
* `purpose`
* `template` (string)
* `input_schema_ref` (optional)
* `output_schema_ref` (optional)
* `created_at`
* `created_by` (user/agent/system)
* `diff_from_version` (optional)

## 3) Invocation logging
When a prompt is invoked:
* store the fully materialised prompt (template + variables) in `ToolRun.inputs_logged`
* store `prompt_id` + `prompt_version` + model id + sampling params in `ToolRun.outputs_logged`

## 4) Governance checks (future linter rules)
* Hard error if a model call lacks `prompt_id` + `prompt_version`.
* Warning if prompt version changes within an active plan project without a corresponding governance note/audit event.

