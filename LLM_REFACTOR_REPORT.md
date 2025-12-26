# Policy & LLM Refactoring Report

## Completed Tasks
1.  **`LLMProvider` Architecture**:
    *   Defined strict interface in `tpa_api.providers.llm`.
    *   Implemented `OpenAILLMProvider` with full `ToolRun` provenance.
2.  **Prompt Governance**:
    *   Created `PromptService` to handle versioned registration of prompts in the database.
    *   Ensured all LLM calls register their prompt templates before execution.
3.  **Policy Extraction Modularization**:
    *   Extracted logic from `ingest_worker.py` into `tpa_api.ingestion.policy_extraction`.
    *   Refactored `extract_policy_structure`, `extract_policy_logic_assets`, and `extract_edges` to use the new provider stack.
4.  **Ingestion Graph Update**:
    *   Updated `ingestion_graph.py` to use the new clean modules.
5.  **Documentation**:
    *   `PROMPT_ENGINEERING_GUIDE.md` added to root.

## Result
The system now treats Prompts as first-class governance artefacts and LLM calls as traceable infrastructure events. No logic remains hidden in the worker monolith.
