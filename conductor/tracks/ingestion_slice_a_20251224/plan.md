# Track Plan: Ingestion Pipeline (Slice A)

## Phase 1: Environment & Database Scaffolding
- [ ] Task: Verify Database Migrations for Ingestion Tables (`documents`, `pages`, `chunks`, `policy_sections`, `policy_clauses`)
- [ ] Task: Implement/Verify `BlobStoreProvider` (MinIO) integration for raw PDF storage
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Environment & Database Scaffolding' (Protocol in workflow.md)

## Phase 2: DocParse & Structural Extraction
- [ ] Task: Write Tests for `DocParseProvider` (Docling integration)
- [ ] Task: Implement `DocParseProvider` to extract structured text and layout from PDF
- [ ] Task: Write Tests for Canonical Loading (`Document`, `Page`, `Chunk` persistence)
- [ ] Task: Implement Persistence Logic for structural parsing results
- [ ] Task: Conductor - User Manual Verification 'Phase 2: DocParse & Structural Extraction' (Protocol in workflow.md)

## Phase 3: Policy Atomization (LLM)
- [ ] Task: Write Tests for Policy Section/Clause extraction logic
- [ ] Task: Implement LLM-based Policy Structure Extraction (transforming DocParse output into `policy_sections` and `policy_clauses`)
- [ ] Task: Write Tests for Metadata Extraction (e.g., policy IDs, references)
- [ ] Task: Implement Extraction of policy metadata during atomization
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Policy Atomization (LLM)' (Protocol in workflow.md)

## Phase 4: Vectorization & Retrieval
- [ ] Task: Write Tests for `EmbeddingProvider` (Qwen3 integration)
- [ ] Task: Implement Text Vectorization for policy chunks
- [ ] Task: Write Tests for Basic Retrieval (`RetrievalProvider` search functionality)
- [ ] Task: Verify end-to-end Slice A flow: PDF -> Database -> Search Result
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Vectorization & Retrieval' (Protocol in workflow.md)
