# Reasonableness Linter Specification


## Output
The linter produces a `GovernanceReport` for every Run (`schemas/GovernanceReport.schema.json`).

## Hard Checks (Errors)
1. **Uncited Policy/Law/Factual Claim**: `Interpretation` marked as policy/law/fact is missing `EvidenceRef`.
2. **Missing Judgement Trace**: Judgement outputs lack `context_bundle_ref`, `tool_run_ids`, or `prompt_id`/`prompt_version`.
3. **Implicit Assumption**: `Interpretation` relies on facts not present in its context bundle.
4. **Leaked IDs**: Final sheet output contains internal UUIDs.
5. **Unversioned Prompt**: Any `ToolRun` for `LLMProvider`/`VLMProvider` is missing `prompt_id` or `prompt_version` in `outputs_logged` (see `platform/PROVIDER_INTERFACES.md`).

Defaulting rule:
* If `claim_kind` is missing, the linter treats the claim as **policy/law/fact** and requires `EvidenceRef`.

## Soft Checks (Warnings)
1. **Strained Interpretation**: `Interpretation.confidence < 0.4` (when provided) but presented as fact.
2. **Evidence Gap**: Issue marked "Material" but has 0 Evidence Atoms.
3. **Single Source**: Crucial issue relies on only 1 evidence source.
