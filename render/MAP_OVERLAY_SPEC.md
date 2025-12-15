# Map Overlay Specification

## Requirement
The system must generate a Leaflet/Mapbox compatible tile layer or image overlay for:
1. Site Boundaries.
2. Sensitivity Heatmaps.
3. "Plan Reality" Overlays (Georeferenced Plans).

## Registration
* Uses `ProjectionArtifact` from ingest pipeline.
* Renders using GDAL/Rasterio (Python part) to produce XYZ tiles.
