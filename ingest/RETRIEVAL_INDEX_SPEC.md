# Retrieval Index Specification

## Index Structure
* **Chunks/Clauses Index**: Text + Embedding + rich metadata.
  * Minimum metadata: `authority_id`, `document_id`, `doc_type`, `published_date`, `page`, `section_path`
  * Policy-aware metadata where available: `policy_id`, `policy_clause_id`, `policy_topic_tags[]`
  * Every record must be resolvable to an `EvidenceRef`.
* **Visuals Index**: Description + Embedding + image/plan metadata.
  * Minimum metadata: `authority_id`, `asset_id`, `source_document_id`, `page`, `asset_type`
  * Every record must be resolvable to an `EvidenceRef` (e.g., `asset::...::...`).

## Search Logic (Hybrid)
Hybrid retrieval is required, but the merge policy is **configuration**, not hard-coded.

Examples:
* RRF merge of (keyword results + vector results)
* Weighted merge: `vector_search(q) * 0.7 + keyword_search(q) * 0.3`

The retrieval provider is an evidence instrument: the system must log query inputs/outputs as `ToolRun` and treat results as *candidates* to be curated, not determinations.

## Retrieval frames (planner-shaped queries)
Most retrieval is not “free text search”; it is a **retrieval frame** assembled by agents and tools, typically including:
* `topic` / question focus (design, transport, housing, etc.)
* `authority_id`
* `culp_stage_id` (plan-making) or `application_id` (DM)
* `site_geometry` / spatial filters (buffers, zones, admin area)
* `document_type` / adoption status / effective date filters

The frame must be logged as part of the retrieval `ToolRun.inputs_logged` to support replay and contestability.

## Providers
* **Azure**: Azure AI Search.
* **OSS**: PgVector (with IVFFlat or HNSW) + GIN Index for FTS.

## Chunking policy (authority documents)
To support planner-shaped retrieval, ingestion should favor:
* heading-/clause-aware chunks for policy documents (instead of fixed-size windows)
* stable `section_path` and clause identifiers that can be cited and replayed
