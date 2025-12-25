# Plan <-> Reality (Slice B) Specification


This component handles the registration of "Plans" (PDF/Images) to "Reality" (GIS World).

This is a **slice acceptance test spec**; see `tests/SLICES_SPEC.md` for how slices are used to drive implementation and testing.

## Requirements
* **Tier 0 Registration**: Every visual asset must have a `Frame` (image-space). A `Transform` (world matrix)
  exists only when georeferencing succeeds; otherwise the run must record an explicit skip or failure.
* **SAM2 Segmentation (Raster)**: Use SAM2 to extract features from **raster** plans/images (north arrows, scale bars, boundaries, key symbols).
  * This is implemented via the `SegmentationProvider` interface (see `platform/PROVIDER_INTERFACES.md`).
  * Vector geoprocessing (buffers/intersections/tiling) is handled by GIS tools (PostGIS/GeoPandas/GDAL) and logged as `ToolRun`s, not by the segmentation provider.
  * If raster features must be digitised into **vector geometry** (e.g., turn a redline boundary into GeoJSON), treat this as a separate evidence instrument (optional `VectorizationProvider`), log it as a `ToolRun`, and store the vector output as an artefact with explicit limitations.
* **Overlays**: Must produce `ProjectionArtifact` (the plan warped onto the map).
* **Redline detection**: When the asset is map-like, prompt SAM2 to segment redline boundaries and key legend symbols; store masks + derived vectors with explicit limitations.
* **No timeouts**: georef runs are not time‑limited; cancellation is operator‑driven.

## Agentic georeferencing loop
Auto-georef is attempted **only when worthwhile** (map-like cues detected). The agentic loop is executed via a macro toolchain:
* `export-map-observation` (snapshot for visual QA)
* `detect-candidate-gcps` (grid/road/label anchors)
* `apply-gcps` (warp with GDAL TPS/affine/polynomial as appropriate)
* `evaluate-georef` (RMSE + alignment metrics)
* `publish-outputs` (GeoTIFF + overlays + provenance)

Hard failures are allowed but must be logged in `tool_runs` with explicit reasons. Skips are also logged with
`georef_status=skipped` and a `georef_skip_reason`.

Defaults:
* Target CRS: **EPSG:27700** (override only when explicit graticules/metadata indicate otherwise; log `source_crs_guess`).
* Reference layer: **OSM** (override via config; log `TPA_GEOREF_REFERENCE_LAYER`).
* Success threshold: `TPA_GEOREF_RMSE_THRESHOLD` (tweakable).

The output is only valid if a `Transform` exists; otherwise the attempt is reported as unsuccessful.

## Uncertainty
* Every transform has an `uncertainty_score` (0.0 - 1.0).
* If > 0.5, UI must show a warning: "This overlay is approximate."
* Plan ↔ reality mapping is bidirectional: store both the warped plan overlay and the inverse
  projection artefact so evidence can be traced from map → plan and plan → map.
