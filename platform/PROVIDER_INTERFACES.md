# Provider Interfaces (Contract)

This document specifies the **provider contract** used to enforce the “two complete profiles / no hybrid runtime” rule.

Providers are *infrastructure + model* adapters. They never contain planning logic. Planning logic lives in the core services (ingestion, KG, grammar orchestrator, renderer, governance).

## 1) ProviderProfile loading (no hybrid runtime)

### 1.1 Profile selection
A deployment selects **exactly one** profile file:
* `profiles/azure.yaml`
* `profiles/oss.yaml`

The runtime must fail fast if:
* a provider name is missing for a required interface, or
* a provider from a different profile-family is loaded (“hybrid”).

### 1.2 Profile-family identity
Every concrete provider must declare a `profile_family`:
* `azure`
* `oss`

The `ProviderProfile.profile` value must match the `profile_family` of **all** instantiated providers.

### 1.3 Provenance invariant (applies to all providers)
Every provider call that creates derived outputs MUST be logged as a `ToolRun` and linkable to downstream `EvidenceRef`s.

## 2) Shared data types (language-agnostic)

### 2.1 EvidenceRef (string form)
Evidence pointers MUST use the canonical string form described in `db/PROVENANCE_STANDARD.md` and `schemas/EvidenceRef.schema.json`:
`{source_type}::{source_id}::{fragment_selector}`

### 2.2 ToolRun (logging envelope)
Providers MUST emit a `ToolRun` record (shape in `schemas/ToolRun.schema.json`) including:
* inputs (logged)
* outputs (logged)
* status + timestamps
* provider/model identifiers where applicable

## 3) Interface specifications

Each interface defines:
* required methods
* minimum logging/provenance behavior
* error semantics (what must be surfaced vs retried)

### 3.1 `BlobStoreProvider`
**Purpose**: durable object storage for raw inputs and derived artefacts.

**Required methods**
* `put_blob(path, bytes, content_type, metadata) -> {path, etag, size_bytes}`
* `get_blob(path) -> {bytes, content_type, metadata}`
* `delete_blob(path) -> void`
* `exists(path) -> bool`

**Provenance**
* `put_blob` must return stable `path` for referencing from `artifacts.path` and evidence cards.

### 3.2 `CanonicalDBProvider`
**Purpose**: canonical state + KG tables, always PostgreSQL (hosted or self-hosted).

**Required methods**
* `execute(sql, params?) -> rows`
* `execute_one(sql, params?) -> row`
* `transaction(fn) -> result` (commit/rollback)

**Provenance**
* DB writes created from tools/providers must include `tool_run_id` and/or `evidence_ref_id` per `db/DDL_CONTRACT.md`.

### 3.3 `RetrievalProvider`
**Purpose**: index + retrieve chunks/clauses/visual descriptions.

**Required methods**
* `upsert(index_name, records[]) -> void`
* `delete(index_name, record_ids[]) -> void`
* `search(index_name, query, filters?, top_k?) -> results[]`

**Result shape (minimum)**
Each result must include:
* `record_id`
* `score`
* `evidence_ref` (or a resolvable pointer to one)
* `metadata` (authority/site/doc ids, etc.)

**Hybrid retrieval**
The provider must support:
* keyword search
* vector search
* a merge strategy (e.g. RRF)

The exact strategy is configured per profile; the core logic treats it as an evidence instrument, not a decision engine.

### 3.4 `DocParseProvider`
**Purpose**: parse documents into a normalized structure used by ingestion.

**Required methods**
* `parse_document(blob_path, options?) -> DocParseResult`

**DocParseResult normalization**
Must conform to `ingest/DOC_PARSE_SPEC.md` (pages, chunks, tables) and produce stable fragment selectors suitable for `EvidenceRef`.

### 3.5 `EmbeddingProvider`
**Purpose**: produce embeddings for retrieval/reranking.

**Required methods**
* `embed_text(texts[], options?) -> vectors[]`
* `embed_image(images[], options?) -> vectors[]` (optional; must advertise capability)

### 3.6 `LLMProvider`
**Purpose**: grammar-bound reasoning and synthesis (text only).

**Required methods**
* `generate_structured(messages[], json_schema, options) -> {json, usage, model_id}`

**Required options + logging**
Callers MUST provide (and providers MUST echo into `ToolRun.outputs_logged`):
* `prompt_id` and `prompt_version` (prompt library/versioning for audit)
* sampling params (e.g. `temperature`, `top_p`, `max_output_tokens`) where supported

**Non-determinism is allowed**
The LLM is not required to be deterministic. Instead:
* all prompts, schemas, and outputs must be captured in `ToolRun.outputs_logged`
* replayability is achieved by re-rendering from stored move outputs (see `tests/REPLAYABILITY_SPEC.md`)

### 3.7 `VLMProvider`
**Purpose**: multimodal understanding of plans/images/figures.

**Required methods**
* `generate_structured(messages[], images[], json_schema, options) -> {json, usage, model_id}`

**Required options + logging**
Callers MUST provide (and providers MUST echo into `ToolRun.outputs_logged`):
* `prompt_id` and `prompt_version`
* sampling params (where supported)

### 3.11 Predictable degradation (all providers)
If a required provider/tool is unavailable (quota, model down, missing dependency), the system may fall back to safe heuristics, but must:
* mark the run as `ToolRun.status = partial` (or `error` where no safe fallback exists)
* include `outputs_logged.fallback_mode = true` and a short `outputs_logged.fallback_explanation`
* surface limitations in downstream `Interpretation.limitations_text` / evidence cards and governance warnings

### 3.8 `SegmentationProvider` (raster/image segmentation)
**Purpose**: promptable segmentation for **raster** inputs (plans, photos), producing masks and confidence.

This interface is NOT for vector geoprocessing (buffers/intersections). Those are handled by spatial tools (PostGIS/GeoPandas/GDAL) and logged as `ToolRun`s.

**Required methods**
* `segment(image, prompts, options?) -> {masks[], confidence?}`

### 3.9 `WorkflowProvider`
**Purpose**: run orchestration substrate (agent graph execution, background jobs).

**Required methods**
* `run_workflow(workflow_name, inputs, options?) -> {run_handle}`
* `get_status(run_handle) -> status`

### 3.10 `ObservabilityProvider`
**Purpose**: traces, metrics, structured logs.

**Required methods**
* `log_event(name, props)`
* `log_metric(name, value, props?)`
* `start_span(name, props?) -> span_handle` / `end_span(span_handle, status?)`
