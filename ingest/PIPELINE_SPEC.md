# Ingestion Pipeline Specification

## Phases
1. **Raw Ingestion**: Upload blob to `raw/`.
2. **Canonical Extraction**: Parse via DocParseProvider. Extract text, tables, images.
3. **Canonical Loading**: Write to `documents`, `chunks`, `visual_assets`.
4. **Graph Construction**: Create `Chunk` nodes in KG.
5. **Enrichment**:
    * Embed Chunks.
    * Extract "Mentions" (Site/Policy).
    * Create `CITES` and `MENTIONS` edges.

## Invariant
The pipeline must be **Multi-Pass**.
* Pass 1: Structural extraction (fast).
* Pass 2: Vision/Refinement (expensive, async).

## Authority Packs (Policy + GIS bundles)
Authority packs (see `authority_packs/*`) are treated as **ingestion manifests**, not runtime data structures.

### Manifest normalization
The ingestion service must normalize authority pack manifests into a single internal shape (v2-style), so downstream ingestion does not branch on legacy formats.
* Legacy: `documents: [string]`
* v2: `documents: [{title,url,type,status,published_date,file_path,...}]`

This normalization is also the implementation point for the published “**Document Parity Model**”:
* all plan-like documents (Local Plans, SPDs, design codes, evidence base papers) are treated uniformly as `Document` inputs,
* hierarchy and weight are not hard-coded; they are inferred/curated during runs and captured as interpretations/metadata with provenance.

### Authority document chunking (retrieval-first)
Authority policy documents (Local Plans, SPDs, AAPs, design guides) must be chunked to support *planner-shaped retrieval*:
* Prefer **clause- and heading-aware chunks**, not generic fixed token windows.
* Persist `section_path` / heading hierarchy where available (e.g., `Chapter 4 > Policy H1 > Criterion (c)`).
* For policy-like text, create canonical `PolicyClause` units (or clause-marked chunks) suitable for `CITES` edges.
* Where useful, perform **semantic atomisation** into short “policy atoms” (embedding-dense fragments) with:
  * cross-reference signals (`CITES`, clause↔clause links),
  * inferred qualifiers/tests (stored as metadata, not treated as determinations),
  * (when available) geographic applicability hints.
* Attach authority metadata to every chunk:
  * `authority_id`, `plan_name`, `adoption_status`, `published_date`, `document_type`

#### Inference-driven ontology (no fixed taxonomy)
The system must not depend on a frozen topic taxonomy. Instead, ingestion may add **probabilistic metadata** (always with provenance):
* inferred topic tags / policy themes
* inferred triggers/tests (“tall buildings”, “heritage setting”, “sequential test”)
* inferred ambiguities/overlaps (“likely conflicts with …”)

These are retrieval aids and curation hints, not determinations.

### Embedding cascade (multi-scale retrieval)
To support both precise citation and higher-level retrieval, ingestion should store embeddings at multiple scales:
* atom/chunk-level
* clause-level (where `PolicyClause` exists)
* document-level (for coarse filtering)

### Cross-document graph fabric (policy is not a blob)
In addition to canonical tables, ingestion should build a lightweight graph fabric:
* citation links (chunk → clause, clause → clause)
* semantic adjacency links (similarity clusters)
* spatial relevance links (clause/chunk → zones or spatial features where applicable)

These become traversal primitives for agents (context assembly) and must be logged/provenanced as tool runs.

### GIS layer handling
Authority GIS layers are ingested as **spatial datasets/features**:
* Store layer metadata (name/type/url) as canonical dataset records.
* Download/refresh feature data where possible and load to `spatial_features` with provenance.
* Where endpoints are broken/secured (see `missing_data.md`), record explicit gaps as `Assumption(type=data-gap)` during runs rather than silently omitting.

Published “Spatial Analysis Engine” alignment implies:
* maintain a **layer registry** (lineage, quality, refresh cadence) as canonical metadata,
* optionally generate **embedding signatures** for layer metadata (to support semantic spatial retrieval).

## Public data acquisition (scenario inputs)
Spatial Strategy requires dynamic inputs (constraints, baselines, metrics) that may be obtained from public sources and governed web discovery.
This pipeline is specified in `integration/PUBLIC_DATA_SPEC.md` and `integration/PUBLIC_DATA_SOURCES.yaml`.

## Development Management ingestion (applications)
Development management workspaces depend on an ingestion path for applications:
* Create/refresh canonical `applications` records.
* Ingest and parse submission documents into `documents/pages/chunks/visual_assets` with provenance.
* Link documents to the application in canonical tables and via KG edges (e.g., `RELIES_ON`).
* Run **intake extraction** (structured metrics) as a tool-run (`ToolRun`) rather than ad-hoc parsing.

### Live/demo case feeds (connectors)
For demo/sandbox use (and for councils without BOPS integration), the system may seed cases from public aggregators such as UK PlanIt:
* Connector: `planit` (`integration/PLANIT_CONNECTOR_SPEC.md`)
* Output: canonical `applications` created from PlanIt records, with provenance and links back to the authority portal.
* Constraint: treat PlanIt as evidence, not as the system-of-record; workflows must not assume PlanIt provides full document packs.

## Monitoring ingestion (live evidence)
Monitoring and delivery capabilities depend on ingesting live events and time series:
* Ingest monitoring events into `monitoring_events` with provenance.
* Derive monitoring time series (`monitoring_timeseries`) from events and authoritative sources.
* Support adoption baseline snapshots (`adoption_baselines`) as explicit, versioned artefacts.

## 6. Spatial Enrichment (Geospatial Linkages)
An explicit post-processing step running on a GIS worker (e.g., PostGIS or Geopandas).

### Inputs
*   `Site` nodes (GeoJSON Polygons).
*   `Constraints` layer (Flood Zones, Green Belt, etc.).

### Operations
1.  **Topology Check**:
    *   For every `Site`, check intersection with all `Constraints`.
    *   *If True*: Create `INTERSECTS` edge.
2.  **Proximity Check**:
    *   Buffer `Site` by 400m / 800m (Walking distances).
    *   Find `TransportNode` within buffer.
    *   *If Found*: Create `CONNECTED_TO` edge (Property: `distance_m`).
3.  **Containment**:
    *   Is `Site` within `AdministrativeBoundary`?
    *   Create `CONTAINS` edge.

4.  **Opportunity Field Generation** (optional early, required later)
    * Derive continuous surfaces and/or cached metrics used for strategy reasoning:
      - accessibility/catchments (isochrones)
      - centre-of-gravity / town centre influence
      - environmental tolerance proxies (where data supports)
    * Store outputs as artefacts + citeable evidence refs; never present as determinations.

### Output
*   Batch of KG edges written to `kg_edge` with `tool_run_id` provenance (no Cypher runtime required).
