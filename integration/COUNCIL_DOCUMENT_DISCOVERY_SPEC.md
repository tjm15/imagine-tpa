# Council Document Discovery (Web) Specification

This spec defines a governed web discovery workflow used when an authority does not provide a clean API/bulk export for:
* plan PDFs (local plan, SPDs, evidence base topic papers),
* policies maps (PDFs, images, web maps),
* GIS service endpoints (ArcGIS REST, WMS/WFS) linked from council pages.

This workflow is explicitly **not** “scrape the web until something turns up”.
It is a bounded evidence instrument that produces inspectable artefacts and requires human confirmation when ambiguous.

Related specs:
* Public data acquisition principles: `integration/PUBLIC_DATA_SPEC.md`
* Authority pack manifest normalization: `ingest/PIPELINE_SPEC.md`
* Optional web capture provider: `platform/PROVIDER_INTERFACES.md#41-WebAutomationProvider-governed-web-capture`

## 1) Inputs (minimum)
* `authority_id` (authority pack id / canonical authority id)
* `seed_urls[]` (starting points; must be allowlisted)
  - council local plan landing page(s)
  - known “downloads” pages
  - authority pack `interactive_map_url` where available
* `domain_allowlist[]` (hard allowlist of domains)
* `request_budget`
  - `max_pages`
  - `max_bytes_total`
  - `max_depth`
  - `per_domain_rate_limit`

## 2) Outputs (what discovery produces)
Discovery produces a **candidate manifest patch** for ingestion, not immediate ingestion:
* `discovered_documents[]` (PDF/ZIP links + titles + dates + confidence + rationale)
* `discovered_policy_maps[]` (PDF/image/web-map links + metadata)
* `discovered_gis_sources[]` (ArcGIS REST/WMS/WFS endpoints + layer hints)
* `limitations_text` (coverage gaps, blocked pages, licensing notes, request budget reached)

The output MUST be:
* stored as an artefact (JSON) and referenced by `EvidenceRef`,
* logged as `ToolRun` (inputs = seed URLs + budget; outputs = artefact refs + summary),
* reviewable in the UI before being merged into an authority pack ingestion job.

## 3) Discovery algorithm (bounded, replayable)

### 3.1 Pass 1 — Deterministic crawl (default)
1. Fetch seed URLs (HTTP fetch preferred).
2. Extract:
   * absolute/relative links
   * file-type candidates (`.pdf`, `.docx`, `.zip`, `.geojson`, `.shp`, `.csv`)
   * ArcGIS REST signatures (`/ArcGIS/rest/services/`, `MapServer`, `FeatureServer`)
   * OGC signatures (`service=WMS`, `service=WFS`, `GetCapabilities`)
3. Score candidates with deterministic heuristics:
   * proximity to known keywords (“local plan”, “policies map”, “SPD”, “adopted”, “submission”, “evidence base”)
   * link text + surrounding heading hierarchy
   * recency indicators (dates in text/URL)
   * file size (avoid huge files unless explicitly requested)
4. Store:
   * raw HTML
   * extracted link table (JSON) with scores and rationale

### 3.2 Pass 1b — JS-rendered capture (Playwright-backed)
If deterministic HTTP fetch produces no useful links or a JS shell page:
1. Use a headless browser capture (Playwright) via `WebAutomationProvider.render(...)`.
2. Capture and store:
   * rendered HTML
   * screenshot(s)
   * optional network log/HAR (if supported)
3. Re-run deterministic extraction on the rendered HTML snapshot.

### 3.3 Pass 2 — Optional AI-assisted resolver (bounded)
If multiple plausible candidates remain, or titles/dates are ambiguous:
1. Provide the candidate tables + snippets to the LLM/VLM provider.
2. Ask for a **structured proposal**:
   * which links should be treated as authoritative for each artefact type,
   * what is missing (explicit gap list),
   * what needs human confirmation.
3. The AI output must be logged as a `ToolRun` and treated as an **interpretation**, not as truth.

### 3.4 Human confirmation (mandatory when ambiguous)
If more than one candidate meets thresholds for the same artefact type:
* require human confirmation in the UI (select one, or attach manually)
* record an `AuditEvent` with the selected link(s) and rationale

## 4) Merge into ingestion (manifest patching)
The discovery output is applied as a **manifest patch** (not an overwrite) to the authority’s internal manifest representation:
* add documents (URL + metadata)
* add GIS sources (service endpoints + layer hints)
* record discovery provenance (ToolRun ids + evidence refs)

This ensures downstream ingestion can remain deterministic and replayable.

## 5) Failure modes (predictable degradation)
* `request_budget` exhausted → return partial results with explicit limitations.
* blocked by robots/terms → stop and record limitation.
* rate limited (429) → respect `Retry-After`; return partial if exceeded budget.
* authentication required → stop; require manual upload or authorised connector.

