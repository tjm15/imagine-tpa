# Replayability Specification

## Definition
"Replayability" means restarting a run from a `RunContext` and `MoveEvent` log produces the *same structural outcome*.

## The Test
1. Run a session (produces `run_id_A`).
2. Extract inputs + random seed from `run_id_A`.
3. Start `run_id_B` with same inputs + seed.
4. Assert: `run_id_A.final_sheet == run_id_B.final_sheet`.

## Note
Exact prose may vary slightly if temperature > 0, but the *decisions* (Issue selected, Policy cited) must be identical.
