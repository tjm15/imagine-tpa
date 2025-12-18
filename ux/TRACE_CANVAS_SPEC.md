# Trace Canvas (Graphical Traceability) Specification

Planners do not want to read JSON logs. They want a **flowchart** they can interrogate:
* “How did we get here?”
* “What evidence did this rely on?”
* “What changed since last time?”
* “What was assumed?”

This spec defines a **Trace Canvas** UI that renders run traceability as a **graph**, while keeping the underlying storage machine-readable (`MoveEvent`, `ToolRun`, `AuditEvent`).

## 1) Principle: stored as JSON, *experienced* as a flowchart
The system stores:
* `MoveEvent[]` (8‑move procedure log) (`schemas/MoveEvent.schema.json`)
* `ToolRun[]` (all tool/model calls) (`schemas/ToolRun.schema.json`)
* `AuditEvent[]` (human selections/accept/reject/sign-off) (`schemas/AuditEvent.schema.json`)

The UI presents a **deterministic projection** of those records as a `TraceGraph`:
* `schemas/TraceGraph.schema.json`

## 2) The flowchart model (TraceGraph)

### 2.1 Node types (planner-legible)
Minimum node types:
* `run` (RunContext anchor)
* `move` (one of the 8 moves)
* `tool_run` (retrieval, spatial op, instrument call, model call)
* `evidence` (EvidenceAtom / EvidenceCard)
* `interpretation` (what evidence means here)
* `assumption` (explicit gap-filling)
* `ledger` (considerations)
* `weighing` (trade-offs / decisive factors)
* `negotiation` (alterations/deltas)
* `output` (Trajectory, ScenarioJudgementSheet, document draft pack)
* `audit_event` (user selected tab, accepted suggestion, signed off)

### 2.2 Edge types (how information flowed)
Minimum edge types:
* `TRIGGERS` (audit event → workflow/move)
* `USES` (move/tool → evidence)
* `PRODUCES` (move/tool → output artefact)
* `CITES` (output → EvidenceRef)
* `ASSUMES` (interpretation/output → assumption)
* `SUPPORTS` / `CONTRADICTS` (interpretation/ledger → ledger/weighing)
* `SUPERSEDES` (new output replaces prior output; supports diff mode)

### 2.3 Explainability modes
The same run must be viewable at three levels (published architecture “Summary / Inspect / Forensic”):
* `summary`: 8‑move spine + key outputs + top evidence cards
* `inspect`: tool runs, issue clusters, ledger and weighing nodes
* `forensic`: prompts/model IDs, full tool inputs/outputs links, snapshot/diff nodes

Mode controls how many nodes/edges are shown, not what is stored.

## 3) Trace Canvas UI (what planners see)

### 3.1 Default view (fast, glanceable)
* An 8‑step horizontal spine (“Framing → … → Positioning”) with status and timestamps.
* For the selected move, a small subgraph shows:
  - evidence cards used
  - tools invoked
  - artefacts produced
  - assumptions introduced
* A “Why?” interaction:
  - click any sentence/claim in a sheet or draft → highlights upstream nodes that support it.

### 3.2 Drill-down interactions
* Click `tool_run` node → shows inputs, outputs, limitations, provider/model and prompt version.
* Click `evidence` node → opens the source fragment (page/snippet/map overlay) and any limitations.
* Click `assumption` node → shows scope + justification and where it was used.
* Click `audit_event` node → shows what the user did (accepted/rejected/signed-off), and which snapshot/run state was active.

### 3.3 Diff mode (what changed)
Planners constantly ask “what changed since last draft / last meeting / last scenario run?”.
The Trace Canvas must support comparing:
* two runs (`run_id_A` vs `run_id_B`), or
* two tabs (Scenario×Framing), or
* two snapshots (optional early, recommended for sign-off) (`schemas/Snapshot.schema.json`, `schemas/SnapshotDiff.schema.json`).

Diff view requirements:
* highlight added/removed/changed nodes (evidence changed, tool outputs changed, assumptions changed)
* show a short “delta explainer” narrative backed by edges (no uncited summary)

### 3.4 Export (defensibility)
One click export must produce a shareable artefact (for managers/inspectors/legal):
* trace graph image (SVG/PDF)
* evidence bundle index
* run metadata (profile, prompt versions, key tool runs)

## 4) Implementation notes (how to build it)
* Build `TraceGraph` deterministically from stored tables (no model calls).
* Use a graph layout library (Dagre/ELK) client-side or server-side.
* Store graph layout hints optionally so replays are stable.

This keeps “clever architecture” invisible until it is needed — then instantly inspectable.
