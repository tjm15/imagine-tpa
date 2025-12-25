# Map Overlay Specification
> WARNING: This spec is provisional/outdated/incomplete. TODO: review and update.


## Requirement
The system must generate a Leaflet/Mapbox compatible tile layer or image overlay for:
1. Site Boundaries.
2. Sensitivity Heatmaps.
3. "Plan Reality" Overlays (Georeferenced Plans).
4. Policies map drafts/finals (where vector geometries exist).

## Registration
* Uses `ProjectionArtifact` from ingest pipeline.
* Renders using GDAL/Rasterio (Python part) to produce XYZ tiles.

## Photomontage / viewpoint artefacts (Reality Mode)
Photomontages are not map tile layers, but they are still citeable visual outputs.

Requirement:
* store photomontages as `ProjectionArtifact(artifact_type=photomontage)` (or `VisualAsset(asset_type=photomontage)` where ingested)
* surface them as EvidenceCards (`card_type=photomontage`) with limitations and uncertainty where transforms are used
