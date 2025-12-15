# Provenance Standard

## 1. Evidence References
Every claim in the system must be backed by an `EvidenceRef`.
Format: `{source_type}::{source_id}::{fragment_selector}`
Example: `doc::doc-123::page-4-para-2`

## 2. Tool Runs
Every automated process must produce a `ToolRun` record.
* Inputs must be captured.
* Outputs must be captured.
* Logs/Errors must be captured.

## 3. Assumptions
If no evidence exists, an `Assumption` must be created.
It is ILLEGAL to hallucinate or infer without declaring it as either an Interpretation (backed by evidence) or an Assumption (explicitly unfounded).
