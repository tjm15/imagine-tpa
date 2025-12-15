# Invariant Tests Specification

## Grammar Completeness
* Test: Traverse `MOVE_IO_CATALOGUE.yaml`. Ensure every output schema exists in `schemas/`.
* Test: Ensure every Agent implementation in `agents/` maps to a move.

## Provenance Enforecement
* Test: Scanning the DB, ensure 0 rows in `kg_edge` have null `evidence_ref` AND null `tool_run_id`.

## Schema Backward Compatibility
* Test: Changes to `MoveEvent` schema must be non-breaking (add fields only).
