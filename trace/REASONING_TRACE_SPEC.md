# Reasoning Trace Specification


## Purpose
Define a planner-legible **ReasoningTrace** that records how a judgement output was assembled without
forcing determinism or replayability. The trace is an **audit trail**, not a decision engine.

Key principles:
* **Traceability over determinism**: no replay requirement.
* **Planner-legible**: traces must support a graphical "how we got here" view.
* **Separation of outputs**: internal model reasoning (if captured) is stored independently from
  the main UI output to avoid duplication and leakage.
* **Judgement allowed**: subjective, creative, and framing-dependent judgement is permitted downstream,
  but must remain clearly marked as judgement.
* **Citations still required**: policy/legal/factual claims must carry `EvidenceRef`s even when a
  trace exists.

## What a ReasoningTrace contains
A ReasoningTrace is a bundle of **references** to:
* context bundles (what evidence was assembled),
* tool runs (what instruments were invoked),
* prompt versions (what structured prompts were used),
* model outputs (main output + optional internal reasoning),
* forensic artefacts (optional).

It does **not** store output verbosity or UI-only presentation modes.

## Capture levels (trace only)
Capture level is **inferred** (e.g., by an LLM-as-judge) and stored for audit. Labels are stable and
can be remapped in UI copy:
* `summary`
* `inspect`
* `forensic`

Capture level is about **how much trace is retained**, not how verbose the UI text is.
Capture level is not used for reasonableness linting.

## Two-stage model outputs (main + reasoning)
Some models (e.g., GPT-OSS) emit:
* **Main output**: the text/JSON that powers the interface.
* **Reasoning output**: internal chain-of-thought or scratchpad.

The system **may** store the reasoning output when important, but it must be:
* stored separately from the main output,
* tagged as **forensic only**,
* never surfaced in the standard UI by default.

## Record types (non-exhaustive)
Each trace record is one of:
* `context_bundle_ref`
* `tool_run_ref`
* `prompt_version_ref`
* `model_output`
* `forensic_artifact`
* `note`

## Required traceability rule
Every trace record must point to a durable ID or artefact URI. No free-floating content.

## UI guidance (non-binding)
* The default view should show a **graph/timeline** of context bundles -> tool runs -> outputs.
* Drill-down should show the exact artefacts (snippets, overlays, tool outputs).
* Forensic content must be opt-in.

## Related schema
* `schemas/ReasoningTrace.schema.json`
