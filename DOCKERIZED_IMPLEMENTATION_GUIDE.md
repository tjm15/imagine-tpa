# Dockerised Implementation Guide (Full Stack, No-Hybrid Profiles)

This repo is **spec-first**. This guide shows how to turn it into a **dockerised, end-to-end runnable product** while preserving the core constraints:

* **Dashboard/Digital Case Officer UI is canonical** (`ux/DASHBOARD_IA.md`)
* **Frozen 8-move grammar is the judgement spine** (`grammar/GRAMMAR.md`, `schemas/MoveEvent.schema.json`)
* **No hybrid runtime**: pick exactly one provider family at runtime (**Azure** or **OSS**) (`profiles/*.yaml`, `platform/PROVIDER_INTERFACES.md`)
* **Non-deterministic models are allowed**; replayability comes from stored artefacts + deterministic re-render (`tests/REPLAYABILITY_SPEC.md`)
* **CULP artefacts are hard requirements** (stage gating) (`culp/PROCESS_MODEL.yaml`, `culp/ARTEFACT_REGISTRY.yaml`)

The docker stack described here is designed to support the vertical slices in `tests/SLICES_SPEC.md` (slices are acceptance tests).

---

## 0) What you will end up with

### OSS profile (self-hosted) – docker compose
You will run a stack like:

* `tpa-db` — PostgreSQL + PostGIS + pgvector (canonical store + KG + vectors)
* `tpa-minio` — S3-compatible blob store (artefacts/evidence packs)
* `tpa-redis` — background job queue (ingestion runs, agent runs)
* `tpa-api` — API + orchestration (FastAPI recommended), runs grammar workflows and serves the UI
* `tpa-worker` — tool runner + ingestion + background workflows (can be the same image as API)
* `tpa-ui` — dashboard UI (React/Vite build served by Nginx; scaffold is intentionally minimal)
* Optional “heavy” services:
  - `tpa-llm` / `tpa-vlm` — vLLM OpenAI-compatible servers (GPU recommended)
  - `tpa-embeddings` — embeddings server (TEI or equivalent)
  - segmentation/vectorisation services (SAM2, raster→vector) if you keep them as separate tool runners
  - Playwright-backed web automation runner (for governed acquisition)

### Azure profile (cloud services) – docker for local parity testing
You run the same app containers locally, but they connect to:

* Azure Database for PostgreSQL (+ PostGIS + pgvector)
* Azure Blob Storage
* Azure AI Search
* Azure Document Intelligence
* Azure OpenAI (LLM/VLM/embeddings)

---

## 1) Prerequisites

### Required
* Docker Engine / Docker Desktop
* Docker Compose v2 (`docker compose version`)

### Strongly recommended (OSS “full”)
* NVIDIA GPU + drivers
* NVIDIA Container Toolkit (`nvidia-ctk`), so model containers can use the GPU

### Repo setup
* Copy `.env.example` → `.env` and adjust values (the file is gitignored).

### Version policy (latest-by-default, pin when you need reproducibility)
It’s reasonable to run **latest** (or “latest series”) images during active development, especially while the product surface is still moving fast.

Use the approach that matches your goal:
* **Fast iteration / full features**: float on “latest stable” (default in `docker/compose.oss.yml` via env-substituted image names).
* **Reproducible bug reports / CI**: pin images/tags (or digests) and capture the resolved compose config (`docker compose config`) alongside the run.

In this repo:
* container image choices can be overridden via env vars in `docker/compose.oss.yml`
* Python deps are specified as minimum versions in `apps/api/requirements.txt` (installs newest available at build time)
* the PostGIS+pgvector DB image is built from `docker/db/Dockerfile` and supports `POSTGIS_IMAGE` and `PGVECTOR_VERSION` build args
* vision tool runners default to `python:3.13-slim` (unversioned `python:slim` can jump to new majors and break binary wheels for `numpy`/`opencv`)

---

## 2) Start with the OSS stack (scaffold)

This repo now ships a minimal runnable scaffold:
* `docker/compose.oss.yml` (stack)
* `apps/api` (FastAPI scaffold that serves the spec pack)
* `apps/ui` (React/Vite “Strategic Home” scaffold)

### Step 2.1 — Configure `.env`
From repo root:

```bash
cp .env.example .env
```

Edit `.env` (at minimum: Postgres + MinIO secrets).

### Step 2.2 — Boot the OSS stack
```bash
docker compose -f docker/compose.oss.yml up -d --build
```

If you see `tpa-minio-init` fail, it usually means MinIO wasn’t ready yet or credentials are invalid. Check:
* `TPA_S3_ENDPOINT` is `http://tpa-minio:9000` (inside-compose endpoint, not `localhost`)
* `TPA_S3_SECRET_KEY` / `MINIO_ROOT_PASSWORD` is at least 8 characters

### Step 2.3 — Verify
* API health: `http://localhost:${TPA_API_PORT:-8000}/healthz`
* UI: `http://localhost:${TPA_UI_PORT:-3000}`

The scaffold UI should show CULP stages and required artefacts (stage gate panel semantics).

### Step 2.4 — Boot the “full featureset” profiles (optional)
This compose file includes opt-in profiles for heavier capabilities:
* `ui-dev` — Vite dev server (hot reload)
* `web` — Playwright-backed web automation service
* `vision` — segmentation + raster→vector tool services (CPU heuristic scaffold; swap to SAM2/ML later)
* `models` — LLM/VLM/embeddings servers (GPU recommended)
* `full` — convenience profile that enables `web` + `vision` + `models`

Examples:
```bash
# Full capability stack (expect large downloads / GPU requirements)
docker compose -f docker/compose.oss.yml --profile full up -d --build

# UI dev server instead of the production-like Nginx UI container
docker compose -f docker/compose.oss.yml --profile ui-dev up -d --build
```

---

## 3) Make the DB contract real (migrations)

Right now, `db/DDL_CONTRACT.md` describes tables, but doesn’t ship SQL migrations.

### Step 3.1 — Add migrations
Recommended:
* `db/migrations/0001_init.sql` (canonical tables + procedure tables + KG tables + provenance tables)
* `db/migrations/0002_indexes.sql` (GIN/ivfflat/hnsw, spatial indexes)

### Step 3.2 — Run migrations as a container job
Add a one-shot compose service (example pattern):
* `tpa-migrate` using the same image as `tpa-api`
* command: `python -m tpa_api.migrate`

**Rule**: DDL must be identical in OSS and Azure profiles (only connection/provider differs).

---

## 4) Implement provider adapters behind the profile contract

The core rule is “one logical system, two profiles”:
* logic is provider-agnostic
* profile selects concrete providers

### Step 4.1 — Make profile selection explicit in the app
Implement a startup check:
* read `TPA_PROFILE` (`oss` or `azure`)
* load exactly one profile file (`profiles/oss.yaml` or `profiles/azure.yaml`)
* fail fast if providers cross families (no hybrid)

### Step 4.2 — Provide OpenAI-compatible model endpoints (OSS)
Most OSS implementations converge on OpenAI-compatible HTTP endpoints so your `LLMProvider`/`VLMProvider` are thin adapters.

Bring up model services:
```bash
docker compose -f docker/compose.oss.yml --profile models up -d
```

Practical notes:
* This will download very large models unless you mount pre-downloaded weights.
* For dev without GPU, run “mock providers” (a small internal service that returns schema-valid JSON) so you can build UI + orchestration first.

---

## 5) Make the “Senses” layers real (ingestion)

This is where the system becomes useful.

### Step 5.1 — Authority pack ingestion (text + policy atoms)
Implement ingestion jobs that:
1. load an authority pack manifest (or discovered manifest patch)
2. download/store documents as blobs
3. parse into pages/chunks (`DocParseProvider`)
4. chunk **clause-aware** and atomise into “policy atoms” (`ingest/PIPELINE_SPEC.md`)
5. embed + index (`EmbeddingProvider` + `RetrievalProvider`)
6. construct KG edges (`kg/KG_SCHEMA.md`)

Acceptance: **Slice A** (`tests/SLICES_SPEC.md`).

### Step 5.2 — Spatial substrate + fingerprints
Implement spatial ingestion + enrichment:
* ingest constraint/designation layers
* compute `INTERSECTS`/distance edges for sites
* expose `get_site_fingerprint(site_id)` as a typed tool for agents

Acceptance: **Slice C**.

### Step 5.3 — Visual context layer
Implement:
* `VisualAsset` storage + indexing
* `SegmentationMask` + `VisualFeature` extraction
* registration + overlays with uncertainty (Slice B)

Acceptance: **Slice B** + **Slice I**.

---

## 6) Implement the agent runtime (Orchestration)

### Step 6.1 — Workflow substrate
OSS profile:
* LangGraph-based workflow runner (`WorkflowProvider`)

Azure profile:
* Microsoft Agent Framework / Semantic Kernel lineage (`WorkflowProvider`)

### Step 6.2 — Grammar run per Scenario×Framing tab
Implement:
* `ScenarioSet` → `ScenarioFramingTab[]`
* run 8 moves per tab, storing each move as `MoveEvent`
* all tool/model calls as `ToolRun`
* governance lint on outputs (`governance/REASONABLENESS_LINTER_SPEC.md`)

Acceptance: **Slice E**.

---

## 7) Deterministic rendering + graphical traceability

### Step 7.1 — Render sheets deterministically
* LLM produces structured objects only (schemas)
* renderer converts those objects into HTML sheets (`render/HTML_COMPOSER_SPEC.md`)

Replayability:
* re-render must not require model calls (`tests/REPLAYABILITY_SPEC.md`)

### Step 7.2 — Trace Canvas (flowchart)
* store procedure as JSON (`MoveEvent`, `ToolRun`, `AuditEvent`)
* project to a deterministic `TraceGraph` for UI (`schemas/TraceGraph.schema.json`)
* support diff mode (runs or snapshots) (`schemas/Snapshot.schema.json`, `schemas/SnapshotDiff.schema.json`)

Acceptance: **Slice F**.

---

## 8) Build the planner-grade dashboard UI (UI-first)

Implement in the order suggested in `IMPLEMENTATION_PLAN.md`:
1. Strategic Home (timeline + stage gates + audit ribbon)
2. Living Document editor (WYSIWYG + citations + evidence shelf)
3. Judgement Mode (Scenario×Framing tabs + sheets)
4. Map Mode (draw-to-ask + snapshot)
5. Trace Canvas (flowchart + “why chain”)
6. Draft launcher (DraftRequest → DraftPack suggestions + accept/reject audit)

The UI is where the system “feels” explainable; JSON logs are not the product.

---

## 9) Dynamic public data acquisition (Playwright)

When there’s no clean API/bulk export:
* use governed capture + link extraction (`integration/COUNCIL_DOCUMENT_DISCOVERY_SPEC.md`)
* archive HTML + screenshot artefacts for contestability
* require human confirmation when ambiguous

This is implemented as a tool/instrument with `ToolRun` logging, not as an invisible crawler.

---

## 10) Azure profile parity testing (local docker → cloud services)

### Step 10.1 — Create `.env.azure`
You will need Azure credentials and endpoints:
* `AZURE_POSTGRES_DSN`
* `AZURE_BLOB_CONNECTION_STRING`
* `AZURE_AI_SEARCH_*`
* `AZURE_DOC_INTELLIGENCE_*`
* `AZURE_OPENAI_*`

### Step 10.2 — Boot the Azure parity compose
```bash
docker compose -f docker/compose.azure.yml up -d --build
```

Goal:
* the same slice tests pass (A/B/C/E/F/…)
* with Azure providers only

---

## 11) How to treat “full dockerised” in practice (two tiers)

### Tier 1 — Product development (fast)
* Use OSS stack with mock model providers (or small models).
* Build UI + orchestration + provenance + rendering first.
* Only then turn on GPU model services.

### Tier 2 — Real capability (heavy)
* Turn on models (vLLM + VLM + embeddings).
* Add segmentation/vectorisation services.
* Add real authority ingestion + PlanIt seeding for DM.

This keeps the system implementable while preserving the planner-first UX.
