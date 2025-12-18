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

### Output
*   Batch of `Edge` objects written to the KG (e.g., Cypher statements).

