# Retrieval Index Specification


## Index Structure
TPA uses multiple retrieval lanes. Each lane has its own index family and evidence binding.

### Text lane (dense + FTS hybrid)
* **Chunks/Clauses Index**: text + embedding + rich metadata.
  * Model: Qwen3-Embedding-8B (dense vector).
  * Minimum metadata: `authority_id`, `document_id`, `doc_type`, `published_date`, `page`, `section_path`
  * Policy-aware metadata where available: `policy_section_id`, `policy_clause_id`, `policy_topic_tags[]`
  * Every record must be resolvable to an `EvidenceRef`.
  * Notes:
    - “Policy atoms” are an indexing concept: short, embedding-dense fragments derived from policy documents and stored as chunk/atom records with stable citation selectors.

### Visual page lane (layout-aware, multi-vector)
* **Page Visual Index**: page image + multi-vector embedding + page metadata.
  * Model: `nomic-ai/colnomic-embed-multimodal-7b` (late-interaction / multi-vector).
  * Index full pages by default to preserve layout context and auditability.
  * Minimum metadata: `authority_id`, `document_id`, `page`, `asset_type`
  * Every record must be resolvable to an `EvidenceRef` (e.g., `doc::...::page-...`).

### Visual-text lane (derived text, dense)
* **Derived Visual Text Index**: OCR + captions + linked refs as text.
  * Model: Qwen3-Embedding-8B (dense vector).
  * Only embed after OCR/captions AND linked refs are available.
  * Minimum metadata: `authority_id`, `asset_id`, `source_document_id`, `page`, `asset_type`
  * Every record must be resolvable to an `EvidenceRef` (e.g., `asset::...::...`).

### Structured lane (non-LLM truth)
* **Spatial/Constraint lane**: PostGIS and canonical tables.
  * No embeddings. This is the factual backbone for constraints, geometry, and authoritative IDs.
  * Results must still be resolvable to `EvidenceRef` or a canonical record id with provenance.

## Search Logic (Hybrid + Routing)
Hybrid retrieval is required, but the merge policy is **configuration**, not hard-coded.

### Routing policy (confidence-gated)
* Prefer UI-context routing (visual tab -> visual lane, policy tab -> text lane).
* If context is unknown, use query cues:
  - visual cues: "map", "site plan", "diagram", "table", "photomontage" -> visual page lane
  - policy/legal cues: "policy", "criterion", "exception", "SPD", "NPPF" -> text lane
* Always allow dual-lane retrieval for high-stakes tasks; merge only if neither lane clears confidence.

### Merge examples
* RRF merge of (keyword results + dense results)
* Weighted merge: `vector_search(q) * 0.7 + keyword_search(q) * 0.3`
* Cross-lane merge: `text_lane` + `visual_page_lane` + `structured_lane`, with provenance and confidence flags

The retrieval provider is an evidence instrument: the system must log query inputs/outputs as `ToolRun` and treat results as *candidates* to be curated, not determinations.

## Text reranking (recommended)
* Use a text reranker (e.g., Qwen reranker family) after dense retrieval.
* Typical flow: retrieve 50-200 candidates -> rerank to top 10-30.
* Rerank runs are ToolRuns with model id, prompt or config, and top-k results.

## Retrieval frames (planner-shaped queries)
Most retrieval is not “free text search”; it is a **retrieval frame** assembled by agents and tools, typically including:
* `topic` / question focus (design, transport, housing, etc.)
* `authority_id`
* `culp_stage_id` (plan-making) or `application_id` (DM)
* `site_geometry` / spatial filters (buffers, zones, admin area)
* `document_type` / adoption status / effective date filters

The frame must be logged as part of the retrieval `ToolRun.inputs_logged` to support traceability and contestability.

## Context assembly (multimodal, very-large-context)
Hybrid retrieval is a **candidate generator**, not the whole answer.

Downstream LLM/VLM agents need **multimodal context engineering**, including:
* diversity-aware selection (avoid near-duplicate chunks),
* countervailing evidence surfacing (where plausible),
* KG expansion (bounded multi-hop),
* modality-aware packs (policy / spatial / visual / precedent / consultation).

This is defined as a separate layer (“Context Assembly”), not as “better ranking”.
Spec: `agents/CONTEXT_ASSEMBLY_SPEC.md`.

## Relevance narratives (UI-facing, bounded)
Retrieval is an evidence instrument; the UI must be able to show *why* something surfaced without pretending the rank is a determination.

Recommended pattern:
* retrieval returns candidates,
* agents attach short, structured rationales (“relevance badges”) such as:
  - semantic match
  - spatial trigger
  - cross-reference chain
  - inferred test/exception (explicitly caveated)
* these rationales are logged as interpretations/tool outputs and surfaced in the Live Policy Surface (see `ux/DASHBOARD_IA.md`).

## Providers
* **Azure**: Azure AI Search (text lane); visual lane requires a late-interaction backend (profile-specific).
* **OSS**:
  - Text lane: PgVector (IVFFlat or HNSW) + GIN Index for FTS.
  - Visual page lane: multi-vector/late-interaction backend (e.g., Vespa or equivalent).

## Chunking policy (authority documents)
To support planner-shaped retrieval, ingestion should favor:
* heading-/clause-aware chunks for policy documents (instead of fixed-size windows)
* stable `section_path` and clause identifiers that can be cited and traced

## Visual indexing policy
* Index full pages by default for layout context and auditability.
* Region-level indexes are optional later for highlight/latency optimizations.
* Derived visual text should only be embedded after OCR/captions and linked refs are available.
