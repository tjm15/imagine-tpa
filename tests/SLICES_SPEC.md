# Slice Specifications (Acceptance Tests)

## What a “slice” is
A slice is a **vertical acceptance test**: a minimal, end-to-end capability that proves the system works across ingestion → canonical/KG → grammar → rendering → dashboard affordances **with provenance**.

Slices are not “nice to have features”; they are **testable contracts**.

### Cross-cutting invariants (all slices)
Every slice must satisfy:
1. **Provenance**: all derived outputs link back to `EvidenceRef` and/or `ToolRun` (`db/PROVENANCE_STANDARD.md`).
2. **Grammar-first**: any judgement output is produced through the 8-move grammar and logged as `MoveEvent`s (`grammar/GRAMMAR.md`, `schemas/MoveEvent.schema.json`).
3. **No hybrid runtime**: each slice must run in **exactly one** profile at a time (`profiles/azure.yaml` OR `profiles/oss.yaml`).
4. **Dashboard surface**: outputs must be consumable in the dashboard UI (`ux/DASHBOARD_IA.md`).

Slices should collectively cover the three capability pipelines defined in `capabilities/CAPABILITIES_CATALOGUE.yaml`:
* Spatial Strategy
* Development Management
* Monitoring & Delivery

## Slice A — Document → Chunk → Cite (Text evidence substrate)
**Goal**: Given an authority policy PDF, produce citation-ready chunks and retrieval results that reference stable `EvidenceRef`s.

**Touches**: `BlobStoreProvider`, `DocParseProvider`, `CanonicalDBProvider`, `EmbeddingProvider`, `RetrievalProvider`.

**Pass criteria**
* `documents/pages/chunks` are created (see `db/DDL_CONTRACT.md`) with a stable fragment selector per chunk.
* Retrieval returns results that include an `EvidenceRef` (or a pointer resolvable to one).
* A sample `EvidenceCard` can be built from a retrieved chunk (`schemas/EvidenceCard.schema.json`).

## Slice B — Plan ↔ Reality (Registration + overlays + uncertainty)
**Goal**: Register a raster plan/image to world coordinates and generate an overlay artefact with explicit uncertainty.

**Spec**: `ingest/PLAN_REALITY_SLICE_B_SPEC.md`

**Touches**: `SegmentationProvider` (raster), GIS tools (PostGIS/GDAL), `BlobStoreProvider`, `CanonicalDBProvider`.

**Pass criteria**
* A `ProjectionArtifact` (overlay) is produced and storable as an artefact.
* A `PlanRealityInterpretation` is produced including `uncertainty_score` and limitations (`schemas/PlanRealityInterpretation.schema.json`).
* UI shows a warning when `uncertainty_score > 0.5` (dashboard Judgement/Reality modes).

## Slice C — Spatial enrichment (Site fingerprint)
**Goal**: Precompute spatial relationships (intersections/distances) and expose them as a site fingerprint for reasoning.

**Touches**: GIS tools (PostGIS/GeoPandas), `CanonicalDBProvider`.

**Pass criteria**
* Spatial enrichment writes KG edges (`INTERSECTS`, `NEAR`, `CONNECTED_TO`, etc.) with `tool_run_id` provenance (`kg/KG_SCHEMA.md`).
* `get_site_fingerprint(site_id)` returns precomputed relationships and the underlying provenance pointers.

## Slice D — Instruments as evidence (magpie tools)
**Goal**: Run an external instrument (e.g. flood/connectivity) as an evidence instrument (not a decision engine) with logged inputs/outputs + limitations.

**Touches**: Tool runner + providers used by the instrument, `CanonicalDBProvider`, `ObservabilityProvider`.

**Pass criteria**
* An `InstrumentOutput` object is stored with `limitations_statement` (`schemas/InstrumentOutput.schema.json`).
* The run is logged as `ToolRun`, and the output is surfaced as an `EvidenceAtom`/`EvidenceCard` with limitations.

## Slice E — Full 8-move run (Judgement backbone)
**Goal**: Execute the full 8-move grammar on a fixture context and produce judgement artefacts suitable for review.

**Touches**: retrieval/KG tools + `LLMProvider`/`VLMProvider` as needed, governance linter, renderer.

**Pass criteria**
* All 8 moves produce structured outputs per `grammar/MOVE_IO_CATALOGUE.yaml`.
* Every move is logged as a `MoveEvent` with references to tool runs (`schemas/MoveEvent.schema.json`).
* Governance hard checks pass (`governance/REASONABLENESS_LINTER_SPEC.md`).
* A `ScenarioJudgementSheet` is deterministically rendered from stored structured objects (`render/HTML_COMPOSER_SPEC.md`).

## Slice F — Dashboard affordances (DCO surface)
**Goal**: Prove the dashboard can consume the system outputs in the intended workflow: writing + contextual evidence + judgement review.

**Touches**: UI + API layers; renderer outputs.

**Pass criteria**
* The Living Document can display and accept insertion of `EvidenceCard`s (drag/drop or “insert”) with citations.
* Judgement Mode shows **Scenario × Political Framing** tabs (`ScenarioFramingTab`) and their rendered sheets.
* Selecting a tab produces an explicit `AuditEvent` (no silent agent selection).
* Traceability is available as a **flowchart** (Trace Canvas) derived from `MoveEvent` + `ToolRun` + `AuditEvent` (see `ux/TRACE_CANVAS_SPEC.md`).
* Evidence cards link through to provenance (human-readable) without exposing internal IDs.

## Slice G — DM casework loop (intake → balance → report)
**Goal**: Prove the DM capability chain can run end-to-end for a single application fixture.

**Pass criteria**
* Intake extracts key facts from uploaded docs and logs provenance.
* Material considerations triage produces issues + an issue map.
* Planning balance produces a weighing record.
* Report generation produces a citeable draft section suitable for the Living Document.

## Slice H — Monitoring loop (baseline → trends → triggers → AMR)
**Goal**: Prove monitoring capabilities can compute divergence, propose triggers, and draft AMR narrative from time series inputs.

**Pass criteria**
* Adoption baseline is created and stored with provenance.
* Trend detection and trigger suggestions are logged and traceable.
* AMR draft narrative is produced from structured sources (fact tables/evidence cards), not uncited prose.
