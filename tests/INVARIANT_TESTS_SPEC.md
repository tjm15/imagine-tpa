# Invariant Tests Specification

## Grammar Completeness
* Test: Traverse `MOVE_IO_CATALOGUE.yaml`. Ensure every output schema exists in `schemas/`.
* Test: Ensure every Agent implementation in `agents/` maps to a move.

## Provenance Enforecement
* Test: Scanning the DB, ensure 0 rows in `kg_edge` have null `evidence_ref` AND null `tool_run_id`.

## Schema Backward Compatibility
* Test: Changes to `MoveEvent` schema must be non-breaking (add fields only).

## Slice Coverage
* Test: Every slice in `tests/SLICES_SPEC.md` has at least one executable integration test entrypoint.
* Test: Slice runs must pass governance hard checks (`governance/REASONABLENESS_LINTER_SPEC.md`).

## Capability Catalogue Consistency
* Test: Every capability in `capabilities/CAPABILITIES_CATALOGUE.yaml` references a module in `tools/CAPABILITY_MODULE_REGISTRY.yaml`.
