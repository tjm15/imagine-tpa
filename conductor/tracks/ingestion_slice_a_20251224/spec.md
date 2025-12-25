# Track Spec: Ingestion Pipeline (Slice A)

## Objective
Implement the initial "Slice A" ingestion pipeline to parse authority policy documents (PDFs) into a structured canonical format (policy sections and clauses) in the PostgreSQL database. This enables downstream retrieval and reasoning.

## Scope
- Integration with Docling (OSS DocParseProvider) for structural PDF parsing.
- Implementation of the `CanonicalDBProvider` for persisting documents, pages, chunks, policy sections, and clauses.
- LLM-based policy structure extraction (splitting DocParse output into sections/clauses).
- Embedding generation using Qwen3 for text chunks.
- Basic retrieval interface verification.

## Architecture
- **Worker:** Celery worker running `apps/api/tpa_api/ingestion/worker.py`.
- **Database:** PostgreSQL with PostGIS for canonical storage.
- **Providers:**
  - `DocParseProvider`: Docling-based service (`apps/docparse`).
  - `EmbeddingProvider`: vLLM-based service (`tpa-embeddings`).
  - `LLMProvider`: vLLM-based service (`tpa-llm`).
  - `BlobStoreProvider`: MinIO.

## Data Model (Canonical)
- `documents`: Metadata for the source PDF.
- `pages`: OCR/Structural page records.
- `chunks`: Atomic text fragments for retrieval.
- `policy_sections`: Hierarchical structure (Chapter > Section).
- `policy_clauses`: The actual policy text units.

## Acceptance Criteria
- [ ] PDF documents can be uploaded and structural parsing (Docling) is successful.
- [ ] Text is successfully split into hierarchical sections and clauses using LLM guidance.
- [ ] Embeddings are generated for all chunks and stored in the database.
- [ ] A basic search query returns relevant policy clauses with correct scores.
