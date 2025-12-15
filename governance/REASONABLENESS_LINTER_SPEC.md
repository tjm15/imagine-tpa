# Reasonableness Linter Specification

## Output
The linter produces a `GovernanceReport` for every Run.

## Hard Checks (Errors)
1. **Uncited Claim**: `Interpretation` exists without `EvidenceRef`.
2. **Implicit Assumption**: `Interpretation` relies on facts not in `CuratedEvidenceSet`.
3. **Leaked IDs**: Final sheet output contains internal UUIDs.

## Soft Checks (Warnings)
1. **Strained Interpretation**: VLM confidence < 0.4 but presented as fact.
2. **Evidence Gap**: Issue marked "Material" but has 0 Evidence Atoms.
3. **Single Source**: Crucial issue relies on only 1 evidence source.
