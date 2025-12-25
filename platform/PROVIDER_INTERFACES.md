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

**Multi-lane retrieval**
Retrieval must support separate indexes for:
* dense text (e.g., OCR/clauses/chunks)
* visual pages (layout-aware page retrieval)
Index selection is controlled by `index_name` (e.g., `text_dense`, `visual_pages`).
Reranking is performed via `RerankerProvider` when configured.

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

**Required options**
Callers must be able to select a model/lane via `options.model_id` (e.g., `qwen3-embedding-8b`,
`colnomic-embed-multimodal-7b`). Providers should echo the effective `model_id` in `ToolRun.outputs_logged`.

If a provider supports multi-model embedding in one service, it must accept `model_id` for routing.

### 3.6 `RerankerProvider` (optional but recommended)
**Purpose**: rerank text candidates for higher precision over dense retrieval lanes.

**Required methods**
* `rerank(query, candidates[], options?) -> ranked[]`

**Result shape (minimum)**
Each ranked result must include:
* `record_id`
* `score`
* `metadata` (carry through evidence refs when available)

### 3.7 `LLMProvider`
**Purpose**: grammar-bound reasoning and synthesis (text only).

**Required methods**
* `generate_structured(messages[], json_schema, options) -> {json, usage, model_id}`

**Required options + logging**
Callers MUST provide (and providers MUST echo into `ToolRun.outputs_logged`):
* `prompt_id` and `prompt_version` (prompt library/versioning for audit)

Sampling params are optional. When provided, providers MUST log them. When omitted,
providers SHOULD log the effective parameters used (defaults or model-side settings),
when that information is available.

**Non-determinism is allowed**
The LLM is not required to be deterministic. Instead:
* all prompts, schemas, and outputs must be captured in `ToolRun.outputs_logged`
* traceability is provided via ReasoningTrace bundles + provenance (`trace/REASONING_TRACE_SPEC.md`)

### 3.8 `VLMProvider`
**Purpose**: multimodal understanding of plans/images/figures.

**Required methods**
* `generate_structured(messages[], images[], json_schema, options) -> {json, usage, model_id}`

**Required options + logging**
Callers MUST provide (and providers MUST echo into `ToolRun.outputs_logged`):
* `prompt_id` and `prompt_version`

Sampling params are optional. When provided, providers MUST log them. When omitted,
providers SHOULD log the effective parameters used (defaults or model-side settings),
when that information is available.

### 3.9 Predictable degradation (all providers)
If a required provider/tool is unavailable (quota, model down, missing dependency), the system may fall back to safe heuristics, but must:
* mark the run as `ToolRun.status = partial` (or `error` where no safe fallback exists)
* include `outputs_logged.fallback_mode = true` and a short `outputs_logged.fallback_explanation`
* surface limitations in downstream `Interpretation.limitations_text` / evidence cards and governance warnings

### 3.10 `SegmentationProvider` (raster/image segmentation)
**Purpose**: promptable segmentation for **raster** inputs (plans, photos), producing masks and confidence.

This interface is NOT for vector geoprocessing (buffers/intersections). Those are handled by spatial tools (PostGIS/GeoPandas/GDAL) and logged as `ToolRun`s.

This interface may be used on:
* site plans and drawings (Slice B),
* site photos/streetview captures,
* scanned policy maps (as **raster evidence**).

If you need **digitised vector geometry** from a raster plan/map (e.g., extract boundaries/lines as GeoJSON), use a dedicated digitisation/vectorisation tool and log it as a `ToolRun` (see optional `VectorizationProvider` below).

**Required methods**
* `segment(image, prompts, options?) -> {masks[], confidence?}`

### 3.11 `WorkflowProvider`
**Purpose**: run orchestration substrate (agent graph execution, background jobs).

**Required methods**
* `run_workflow(workflow_name, inputs, options?) -> {run_handle}`
* `get_status(run_handle) -> status`

### 3.12 `ObservabilityProvider`
**Purpose**: traces, metrics, structured logs.

**Required methods**
* `log_event(name, props)`
* `log_metric(name, value, props?)`
* `start_span(name, props?) -> span_handle` / `end_span(span_handle, status?)`

## 4) Optional provider interfaces (v2 / specialised)
Optional interfaces can be implemented per profile without changing the core “no hybrid runtime” rule.
If used, they still MUST emit `ToolRun` logs with full inputs/outputs and limitations.

### 4.1 `WebAutomationProvider` (governed web capture)
**Purpose**: capture and normalise web pages for public data acquisition and council document discovery, including JS-heavy pages (Playwright-backed) when needed.

This provider exists to make web acquisition **inspectable**:
* record what URL was accessed
* record what was clicked/typed (if any)
* store raw HTML + screenshots as artefacts
* surface limitations (rate limits, blocked content, robots/terms constraints)

**Required methods**
* `fetch(url, options?) -> {status, final_url, headers, content_type, body_bytes, artifact_path}`
* `render(url, options?) -> {status, final_url, html_artifact_path, screenshot_artifact_path?, network_artifact_path?}`

**Provenance**
Every call MUST emit a `ToolRun` including:
* request URL + params
* request budget/rate-limit settings used
* returned artefact paths/hashes

### 4.2 `VectorizationProvider` (raster → vector digitisation)
**Purpose**: convert raster plans/maps into vector geometries (polylines/polygons) with confidence and explicit limitations.

This is an evidence instrument for tasks like:
* digitising a boundary from a scanned policies map,
* extracting a site redline boundary from a PDF plan image,
* converting an annotated plan into editable GIS features.

**Required methods**
* `vectorize(image, prompts, options?) -> {features_geojson, confidence?, limitations_text?}`

**Provenance**
Vectorisation outputs MUST be stored as artefacts (e.g., GeoJSON) and referenced via `EvidenceRef` and `ToolRun`.
