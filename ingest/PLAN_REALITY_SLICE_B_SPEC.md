# Plan <-> Reality (Slice B) Specification

This component handles the registration of "Plans" (PDF/Images) to "Reality" (GIS World).

This is a **slice acceptance test spec**; see `tests/SLICES_SPEC.md` for how slices are used to drive implementation and testing.

## Requirements
* **Tier 0 Registration**: Every visual asset must have a `Transform` (World Matrix) or a `Frame`.
* **SAM2 Segmentation (Raster)**: Use SAM2 to extract features from **raster** plans/images (north arrows, scale bars, boundaries, key symbols).
  * This is implemented via the `SegmentationProvider` interface (see `platform/PROVIDER_INTERFACES.md`).
  * Vector geoprocessing (buffers/intersections/tiling) is handled by GIS tools (PostGIS/GeoPandas/GDAL) and logged as `ToolRun`s, not by the segmentation provider.
  * If raster features must be digitised into **vector geometry** (e.g., turn a redline boundary into GeoJSON), treat this as a separate evidence instrument (optional `VectorizationProvider`), log it as a `ToolRun`, and store the vector output as an artefact with explicit limitations.
* **Overlays**: Must produce `ProjectionArtifact` (the plan warped onto the map).

## Uncertainty
* Every transform has an `uncertainty_score` (0.0 - 1.0).
* If > 0.5, UI must show a warning: "This overlay is approximate."
