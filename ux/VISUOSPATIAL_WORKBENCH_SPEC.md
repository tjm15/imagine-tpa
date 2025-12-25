# Visuospatial Workbench Specification (Map / Plan / Photomontage)
> WARNING: This spec is provisional/outdated/incomplete. TODO: review and update.

The Planner’s Assistant must preserve the nuance of planning judgement that happens through **seeing**:
maps, plans, policy maps, photos, and photomontages — not just text retrieval.

This spec defines the visuospatial workbench surfaces and how they integrate with:
* Evidence cards (`schemas/EvidenceCard.schema.json`)
* Judgement tabs (Scenario × Political Framing)
* Trace Canvas (graphical traceability)

## 1) The three canvases

### 1.1 Map Canvas (Map Mode)
Purpose: “Map is a verb” — draw, test, snapshot, cite.

Implementation baseline (OSS):
* Map client: **MapLibre GL JS** (2D)
* Base map: **OpenStreetMap** tiles by default (configurable; consider a local tile server for heavy use)

Required interactions:
* draw marker/lasso → create a geometry query context (buffers, intersects, within-distance)
* toggle layers:
  - baseline constraints/designations
  - scenario overlays (allocations, sensitivity heatmaps, catchments)
  - evidence overlays (policies map, plan overlays)
* measure and annotate:
  - distances
  - areas
  - note pins with EvidenceRefs
* “Snapshot to Document”:
  - export the current view as a `ProjectionArtifact` + `EvidenceCard(card_type=map)`
  - insert into the Living Document with a citation

Traceability:
* Every export/snapshot produces a `ToolRun` and appears in Trace Canvas.

### 1.2 Plan Canvas (Plan / Policy Map viewer)
Purpose: make raster plans and policy maps usable evidence, not dead PDFs.

Required interactions:
* display a `VisualAsset` (PDF page image or extracted image)
* show extracted `VisualFeature`s (north arrow, scale bar, legend, labels) and `SegmentationMask`s
* guided registration workflow (Tier 0):
  - propose control points / features
  - allow human adjustment/confirmation
  - create a `Transform` and `ProjectionArtifact` overlay
* “Export overlay to Map Canvas”:
  - display the warped plan/policy map as an overlay in Map Canvas
  - warn when uncertainty is high

Traceability:
* Registration actions (human and agent) are logged:
  - tool/model calls → `ToolRun`
  - confirmations/edits → `AuditEvent`

### 1.3 Photomontage Canvas (Reality Mode)
Purpose: support visual impact reasoning with explicit uncertainty.

Required interactions (v1):
* view site photos/streetview captures and any ingested photomontages as `VisualAsset`s
* display `ProjectionArtifact(artifact_type=photomontage)` where available
* “Scenario toggle”:
  - switch between scenario overlays in the same viewpoint (when available)
  - otherwise show a “not comparable” state with limitations
* “Quote what’s visible”:
  - select a region and request a structured VLM description (stored as `Interpretation` with limitations)

Additional interactions (v2, but design-critical):
* **Visual diagnostics panel**:
  - show annotated detections (massing blocks, height cues, frontage rhythm hints) as overlays
  - show a short “design intent” interpretation with explicit uncertainty and limitations
* **Comparative visual search**:
  - “find similar schemes / streetscapes” using visual embeddings
  - results are shown as citeable evidence cards with source links (not as approval likelihood)

Traceability:
* any VLM description is a `ToolRun` and is linked to evidence refs (image region selectors).

## 2) How canvases feed judgement and drafting
The canvases are not side-features; they feed the core workbench loops:
* Map snapshots and overlays become EvidenceCards used in:
  - ScenarioJudgementSheets (Judgement Mode)
  - authored plan chapters/policies (Living Document)
* Visual interpretations become `Interpretation[]` feeding:
  - Consideration ledger entries
  - Weighing and balance
* When used in judgement, they must be produced and logged via the grammar (`MoveEvent`).

## 3) Uncertainty and limitations are always visible
Any registration/overlay must carry:
* an uncertainty score
* a limitations statement

UI rules:
* uncertainty > 0.5 shows a visible warning (“approximate overlay”)
* photomontage/viewpoint comparisons must never imply precision where it doesn’t exist

## 4) Artefact outputs (CULP alignment)
CULP requires map-like artefacts:
* `boundary_map`
* `policies_map_draft`
* `policies_map_final`
* `constraints_register`

These must be producible from Map/Plan canvases and tracked in the artefact ledger:
* `culp/ARTEFACT_REGISTRY.yaml`
* `schemas/CulpArtefactRecord.schema.json`
