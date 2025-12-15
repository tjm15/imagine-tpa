# Retrieval Index Specification

## Index Structure
* **Chunks Index**: Text + Embedding + Metadata (Source ID, Page).
* **Visuals Index**: Description + Embedding + Image Metadata.

## Search Logic (Hybrid)
query = `vector_search(q) * 0.7 + keyword_search(q) * 0.3`

## Providers
* **Azure**: Azure AI Search.
* **OSS**: PgVector (with IVFFlat or HNSW) + GIN Index for FTS.
