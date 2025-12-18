# Reasonableness Linter Specification

## Output
The linter produces a `GovernanceReport` for every Run (`schemas/GovernanceReport.schema.json`).

## Hard Checks (Errors)
1. **Uncited Claim**: `Interpretation` exists without `EvidenceRef`.
2. **Implicit Assumption**: `Interpretation` relies on facts not in `CuratedEvidenceSet`.
3. **Leaked IDs**: Final sheet output contains internal UUIDs.
4. **Unversioned Prompt**: Any `ToolRun` for `LLMProvider`/`VLMProvider` is missing `prompt_id` or `prompt_version` in `outputs_logged` (see `platform/PROVIDER_INTERFACES.md`).

## Soft Checks (Warnings)
1. **Strained Interpretation**: `Interpretation.confidence < 0.4` (when provided) but presented as fact.
2. **Evidence Gap**: Issue marked "Material" but has 0 Evidence Atoms.
3. **Single Source**: Crucial issue relies on only 1 evidence source.
