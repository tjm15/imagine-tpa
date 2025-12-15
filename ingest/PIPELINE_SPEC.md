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
