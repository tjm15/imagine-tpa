# Invariant Tests Specification

## Grammar Completeness
* Test: Traverse `MOVE_IO_CATALOGUE.yaml`. Ensure every output schema exists in `schemas/`.
* Test: Ensure every Agent implementation in `agents/` maps to a move.

## Evidence Habit Anchors (Canonical)
* Test: No normative claim without an EvidenceRef (good/bad/acceptable/unacceptable/weight/harm/benefit).
* Test: No policy compliance/conflict claim without a specific policy hook.
* Test: Adopted or emerging status must be explicit; do not assume weight.
* Test: Fact, interpretation, judgement, and recommendation are not collapsed in outputs.
* Test: Weight descriptors must be justified by cited reasoning or evidence.
* Test: Material uncertainty is surfaced in `uncertainty_remaining`.
* Test: Negotiation changes feed back into weighing outputs.

## Provenance Enforecement
* Test: Scanning the DB, ensure 0 rows in `kg_edge` have null `evidence_ref` AND null `tool_run_id`.

## Planning Lifecycle Common Sense
* Test: For each `authority_id`, there is at most one active emerging plan cycle (`status in {'draft','emerging','submitted','examination'}` AND `is_active=true`).
* Test: For each `authority_id`, there is at most one active adopted plan cycle (`status='adopted'` AND `is_active=true`).

## Schema Backward Compatibility
* Rule: Once Phase 0 “contract freeze” is complete (`IMPLEMENTATION_PLAN.md`), changes to `schemas/MoveEvent.schema.json` must be non-breaking (add fields only).
* Test: After freeze, validate that older fixture MoveEvents still validate against the current schema.

## Slice Coverage
* Test: Every slice in `tests/SLICES_SPEC.md` has at least one executable integration test entrypoint.
* Test: Slice runs must pass governance hard checks (`governance/REASONABLENESS_LINTER_SPEC.md`).

## Capability Catalogue Consistency
* Test: Every capability in `capabilities/CAPABILITIES_CATALOGUE.yaml` references a module in `tools/CAPABILITY_MODULE_REGISTRY.yaml`.
