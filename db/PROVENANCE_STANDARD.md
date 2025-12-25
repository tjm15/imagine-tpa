# Provenance Standard


## 1. Evidence References
**Policy/law/factual claims** must be backed by an `EvidenceRef`.
Format: `{source_type}::{source_id}::{fragment_selector}`
Example: `doc::doc-123::page-4-para-2`

Additional common source types (examples):
* Visual assets: `visual::visual-123::region:x1,y1,x2,y2`
* Segmentation masks: `mask::mask-123::label:boundary`
* Overlays / tiles: `projection::proj-123::overlay:full`
* Map snapshots: `map::snapshot-123::viewport:hash`

## 2. Tool Runs
Every automated process must produce a `ToolRun` record.
* Inputs must be captured.
* Outputs must be captured.
* Logs/Errors must be captured.

## 3. Context Bundle Trace (Judgement Outputs)
**Discretionary judgement outputs** are traced through context bundles, tool runs, and prompts.
Minimum fields to record alongside any judgement output:
* `context_bundle_ref` (e.g., `move::move-123::curated_evidence_set` or a pack id)
* `tool_run_ids[]` (retrieval, instruments, model calls)
* `prompt_id` + `prompt_version` (where LLM/VLM is used)

Verbosity is a prompting principle encoded in prompt design and versioning; it is not a runtime field.

Judgement outputs may omit `EvidenceRef`s **only** when they do not state policy, legal, or factual
claims. If a judgement output cites policy/law or asserts a factual premise, it must include
`EvidenceRef`s regardless of trace coverage.

Trace records support procedural transparency; they do not replace citations for reasonableness or
legal weight.

## 4. Assumptions
If no evidence exists, an `Assumption` must be created.
It is ILLEGAL to hallucinate or infer without declaring it as either an Interpretation (backed by evidence or a context bundle trace) or an Assumption (explicitly unfounded).
