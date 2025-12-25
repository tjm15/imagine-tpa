# Public Data & Web Acquisition Specification


Spatial Strategy scenarios require inputs that are not always provided by councils as clean datasets. The system therefore supports **dynamic acquisition** of public data via:
1. **Open APIs** (preferred)
2. **Bulk downloads** (preferred)
3. **Automated web discovery/scraping** (fallback, governed)

All acquisition is treated as an evidence instrument:
* inputs/queries are logged
* raw responses are stored as artefacts where feasible
* outputs are normalised into canonical tables and cited via `EvidenceRef`
* limitations/licensing are recorded and surfaced

## 1) Principles
* **API-first**: prefer official APIs, feeds, and bulk downloads over scraping.
* **Respect constraints**: obey robots.txt where applicable, honour site terms/licensing, rate limit requests, and cache results.
* **Reproducibility**: store raw HTML/JSON/ZIP responses (or hashes if storage is constrained) so the acquisition can be inspected.
* **Human override**: allow manual correction/attachment where automated discovery fails (recorded as an audit event).
* **No hybrid runtime**: acquisition may use external websites/APIs in both profiles, but AI/model calls must still obey the selected profile.
* **External-only budgets**: any request budgets apply only to external APIs/web fetches; ingestion itself has no caps/timeouts.

## 2) Acquisition pipeline stages
### 2.1 Source registry
Sources are declared in `integration/PUBLIC_DATA_SOURCES.yaml` with:
* access method (api/bulk/scrape)
* licensing notes
* refresh cadence
* expected outputs (spatial layers, metrics, documents)

### 2.2 Fetch + archive
Every fetch produces a `ToolRun` and an `Artifact`:
* request URL + headers + timestamp
* response status + content type + size
* stored artefact path (or hash)

### 2.3 Normalise + validate
Convert fetched material into canonical forms:
* documents → `documents/pages/chunks`
* spatial datasets → `spatial_features` (+ layer registry metadata)
* metrics/time series → `monitoring_timeseries` and/or fact tables

### 2.4 Provenance & limitations
For every normalised output:
* create `EvidenceRef`s for citeable fragments
* attach limitations text (coverage gaps, update lag, licensing caveats)

## 3) Web discovery (scraping) – governed fallback
Web discovery is used when:
* a council page has no stable API/bulk export, but publishes PDFs/ArcGIS endpoints, or
* a portal requires navigation to find the final adopted plan documents.

### 3.1 Two-pass approach (deterministic then AI-assisted)
1. **Deterministic crawler**: fetch page(s), extract links, detect file types, identify ArcGIS/WMS/WFS endpoints using heuristics.
   * Use simple HTTP fetch when possible.
   * If the page is JS-rendered or requires interaction to reveal links, use a governed headless browser capture (Playwright-backed) via the optional `WebAutomationProvider` (`platform/PROVIDER_INTERFACES.md`).
   * Store both the raw HTML and a screenshot as artefacts to keep discovery contestable.
2. **AI-assisted resolver** (optional): LLM/VLM interprets messy pages to propose candidate links/endpoints.

Both passes must log:
* raw page snapshots as artefacts
* the extraction outputs (candidate links with confidence + rationale)
* any human confirmations/overrides as audit events

## 4) Safety / compliance controls
* global request budget per job (max pages, max bytes, max domains)
* per-domain rate limits and backoff
* denylist/allowlist of domains per deployment
* licence metadata captured per source and displayed on evidence cards
