# Replayability Specification

## Definition
"Replayability" means a planner can **reconstruct and inspect** a run’s reasoning artefacts and deliverables from the stored procedure log.

Because LLM/VLM providers are allowed to be non-deterministic, replayability is achieved by:
* persisting move outputs (`MoveEvent.outputs`) and tool logs (`ToolRun`)
* deterministically re-rendering sheets from those stored structured objects

## The Test
### 1) Render replay (deterministic)
1. Run a session (produces `run_id_A`), generating `ScenarioJudgementSheet` JSON + rendered HTML.
2. Replay render from stored `MoveEvent` outputs for `run_id_A` (no provider calls).
3. Assert: the replayed `ScenarioJudgementSheet` JSON and HTML are identical to the originals.
4. Build a `TraceGraph` (flowchart projection) for `run_id_A` from stored logs (no provider calls).
5. Assert: the replayed `TraceGraph` is identical (or identical modulo layout coordinates if layout is client-side).

### 2) Re-run invariants (non-deterministic allowed)
1. Start `run_id_B` with the same inputs as `run_id_A`.
2. Assert invariant properties, not exact equality:
   * all 8 move types exist as `MoveEvent`s
   * all `Interpretation.evidence_refs` are non-empty
   * governance hard checks pass (no uncited claims, no leaked IDs)

## Note
Re-running may legitimately choose different issues, policies, or narratives; the system’s correctness is enforced by provenance + governance, not deterministic prose.
