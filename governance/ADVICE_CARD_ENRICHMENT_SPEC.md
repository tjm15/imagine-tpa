# Advice Card Enrichment Specification


## Purpose
Advice Cards are planner-facing, advisory prompts that improve usability and professional quality
without pretending to be policy, evidence, or judgement. They are attached to documents, sections,
policies, or figures as a post-ingestion pass.

## Source Catalogue
The canonical catalogue lives in `governance/GOOD_PRACTICE_CARDS.yaml` and is governed by
`schemas/AdviceCard.schema.json`.

## Output Objects
Instances of Advice Cards are emitted as `AdviceCardInstance` objects (schema
`schemas/AdviceCardInstance.schema.json`). Instances are advisory only and must never be treated
as evidence or determinations.

## When It Runs
Advice Card enrichment is a post-ingestion pass. It may run:
- immediately after ingestion completes, or
- on demand from the debug UI.

This pass must not block core ingestion, and it must be safe to re-run.

## Input Signals
The pass should use the canonical, citable substrate only:
- document identity/status bundles
- section and clause structure
- drawing registers and figure captions
- visual asset types and flags
- map legend/scale/north-arrow presence
- availability of GIS layers

Do not infer judgement outcomes. Use advice cards for navigation and best-practice prompts only.

## Matching Logic
- Prefer deterministic cues first (captions, headings, explicit labels).
- LLM/VLM matching is allowed for ambiguous cues, but results must remain advisory.
- Each instance should record the cues or evidence refs that triggered it.

## De-duplication
- Do not emit the same card more than once for the same scope.
- Use `(card_id, scope_type, scope_id)` as a uniqueness key.

## Trace and Provenance
- Every pass must emit a ToolRun with the catalogue version, model (if any), and prompt version.
- If LLM/VLM is used, store a reference to the prompt version and context bundle.
- Advice cards are not EvidenceRefs; they are annotations linked to EvidenceRefs.

## UI Contract
- Always display the advisory status label.
- Never imply that a card is policy, evidence, or a conclusion.
- Allow dismiss/ignore per user, per scope.
