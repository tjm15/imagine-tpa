# Prompt Engineering Guide

This guide explains how to manage and tweak prompts within the Planner's Assistant (TPA) ingestion and reasoning pipelines.

## 1. Architecture
TPA uses a **Prompt Library** backed by the canonical database. Prompts are not just strings in code; they are versioned governance artefacts.

*   **Prompt Definition**: Stored in `prompts` table (id, name, purpose).
*   **Prompt Version**: Stored in `prompt_versions` table (id, version, template).
*   **Execution**: Handled by `PromptService` and `LLMProvider`.

## 2. Where are prompts located?
Code-side prompt templates are located in:
*   `apps/api/tpa_api/ingestion/policy_extraction.py`: Structural parsing, logic extraction, edge detection.
*   `apps/api/tpa_api/ingestion/prompts_rich.py`: VLM enrichment, imagination synthesis.

When the code runs, it **registers** these templates into the database using `PromptService.register_prompt`.

## 3. How to tweak a prompt?

### Option A: Edit the Code (Developer)
1.  Locate the prompt template variable (e.g., `system_template` in `extract_policy_structure`).
2.  Modify the text.
3.  **Crucial**: Increment the `prompt_version` integer in the `_run_llm_prompt` call (e.g., change `prompt_version=1` to `prompt_version=2`).
4.  Restart the service. The new version will be upserted to the database and used for subsequent runs.

**Example:**
```python
# Old
json_result, _, _ = _run_llm_prompt(
    prompt_id="policy_clause_split_v1",
    prompt_version=1,
    ...
)

# New
json_result, _, _ = _run_llm_prompt(
    prompt_id="policy_clause_split_v1",
    prompt_version=2, # <--- Bump this!
    ...
)
```

### Option B: Database Override (Hotfix)
*Note: This is temporary. Code should eventually catch up.*
1.  Connect to the database.
2.  Insert a new row into `prompt_versions` for the target `prompt_id` with a higher `prompt_version` than what is in the code.
3.  **Warning**: If the code hardcodes `prompt_version=1`, it will technically request version 1. The `PromptService` currently upserts the *code's* version. To support dynamic overrides, the code should be updated to request `version=None` (latest), but currently, it pins versions for reproducibility.
4.  **Recommendation**: Stick to Option A for now to ensure code and DB are in sync.

## 4. Prompt Design Guidelines
*   **JSON Only**: Always instruct the model to `Return ONLY valid JSON`.
*   **Schema Enforcement**: Use `output_schema_ref` where possible to link to a JSON schema validation.
*   **Chain of Thought**: For complex reasoning, ask for a `rationale` field before the final answer in the JSON structure.
*   **Examples**: Few-shot prompting is powerful. Include 1-2 concise examples in the system template if the task is ambiguous.

## 5. Debugging
Every LLM call logs a `ToolRun`.
*   Check `tool_runs` table for `inputs_logged` (contains the exact prompt sent) and `outputs_logged` (raw response + parsed JSON).
*   Use `trace_id` to correlate the LLM call with the parent ingestion operation.
