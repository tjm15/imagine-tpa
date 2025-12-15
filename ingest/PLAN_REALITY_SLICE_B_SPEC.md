# Plan <-> Reality (Slice B) Specification

This component handles the registration of "Plans" (PDF/Images) to "Reality" (GIS World).

## Requirements
* **Tier 0 Registration**: Every visual asset must have a `Transform` (World Matrix) or a `Frame`.
* **Sam2 Segmentation**: Use SAM2 to extract features from raster plans.
* **Overlays**: Must produce `ProjectionArtifact` (the plan warped onto the map).

## Uncertainty
* Every transform has an `uncertainty_score` (0.0 - 1.0).
* If > 0.5, UI must show a warning: "This overlay is approximate."
