# Visual / Visuospatial Reasoning Specification (Visual Context Layer)

TPA must not lose the planner nuance of **visuospatial judgement**:
* maps (constraints, allocations, accessibility catchments, heatmaps),
* plans and policy maps (often raster PDFs/images),
* site photos / streetview captures,
* photomontages and visualisations,
* overlays that show plan ↔ reality translation with explicit uncertainty.

This spec defines the visual context layer as an evidence substrate and reasoning instrument.

## 1) Providers (by profile)
* **Azure**: `VLMProvider = AzureOpenAI` (multimodal), `SegmentationProvider` (SAM2), optional `WebAutomationProvider` for web captures.
* **OSS**: `VLMProvider = NVIDIA-Nemotron-Nano-12B-v2-VL-FP8`, `SegmentationProvider = SAM2`, optional `WebAutomationProvider` (Playwright-backed).

All model outputs must be **structured JSON**, logged as `ToolRun` with prompt versioning where applicable.

## 2) Canonical objects (what must be storable and citeable)
Visual reasoning requires first-class, traceable artefacts:
* `VisualAsset` (plans/photos/photomontages): `schemas/VisualAsset.schema.json`
* `VisualFeature` (north arrow, scale bar, viewpoint marker, etc.): `schemas/VisualFeature.schema.json`
* `SegmentationMask` (SAM2 outputs): `schemas/SegmentationMask.schema.json`
* `Frame` + `Transform` + `ControlPoint` (registration): `schemas/Frame.schema.json`, `schemas/Transform.schema.json`, `schemas/ControlPoint.schema.json`
* `ProjectionArtifact` (overlays/tiles/photomontage outputs): `schemas/ProjectionArtifact.schema.json`
* Interpretations:
  - Plan ↔ reality: `schemas/PlanRealityInterpretation.schema.json`
  - General multimodal interpretations: `schemas/Interpretation.schema.json`

These objects must be referenced via `EvidenceRef` and surfaced as `EvidenceCard`s.

## 3) Visual tasks (planner-shaped, not generic CV)

### 3.1 Plan reading (raster plans / PDFs)
Goal: extract cues that enable registration and interpretation:
* north arrow
* scale bar / dimensions
* boundary and key symbols
* legends and labels

Outputs:
* `VisualFeature[]` (with image-space geometry)
* `SegmentationMask[]` where promptable segmentation is useful (e.g., boundary trace)

### 3.2 Map reasoning (interactive + exported)
Goal: treat maps as an evidence instrument:
* layer toggles, buffers, catchments, constraints
* scenario overlays and deltas
* snapshots and exports that become citeable artefacts

Outputs:
* `ProjectionArtifact` (XYZ tiles / image overlays / snapshots)
* `EvidenceCard(card_type=map|overlay|plan)`

### 3.3 Site photo / streetview understanding
Goal: interpret ground conditions and context while remaining caveated:
* “what is visible here?”
* “what appears constrained/sensitive?”
* “what might be affected visually?”

Outputs:
* `Interpretation[]` with limitations (e.g., seasonality, vantage constraints)

### 3.4 Photomontage / viewpoint reasoning (Tier 1)
Goal: support visual impact reasoning as evidence, not as a vibe:
* store viewpoint identity (where/when/from what direction)
* generate/ingest photomontages and make them citeable
* allow scenario overlays in the same viewpoint where feasible (explicit uncertainty)

Outputs:
* `ProjectionArtifact(artifact_type=photomontage)`
* `Interpretation[]` describing what the montage indicates, with explicit limitations

### 3.5 Design/character reasoning (Visual Context Layer alignment)
Goal: turn drawings, elevations, diagrams, streetscapes, and CGIs into **planning-relevant signals** (not just “object detection”):
* inferred height/scale cues and massing blocks (explicit uncertainty)
* frontage rhythm / grain / plot structure hints
* materiality and roofscape cues (always caveated)
* design-code semantics (setbacks, active frontage, roof form, articulation)

Townscape note (explicitly allowed):
* Townscape assessment may produce **both qualitative judgements** (planner language) and **quantitative proxies** (e.g. estimated storeys, approximate height deltas, view occlusion ratios, skyline line-of-sight hits).
* Quantitative proxies can be **model-derived estimates** or **deterministic calculations** where inputs exist; both are valid evidence instruments when logged.
* These outputs are **never treated as determinations**. They must carry explicit limitations + uncertainty, and can later be improved via fine-tuning/finishing the townscape model.

Outputs (minimum):
* `VisualFeature[]` and/or `SegmentationMask[]` representing detected cues (with confidence + tool_run provenance)
* `Interpretation[]` phrased as planner-legible statements (e.g., “appears 2–3 storeys above established ridge line”), with limitations

Important constraint:
* any “conformance scoring” is treated as an **evidence instrument output** with explicit limitations; it is never treated as a determination.

### 3.6 Comparative visual search (precedent-shaped retrieval)
Goal: allow “find similar schemes” and “find similar street character” interactions using visual embeddings, with provenance:
* store visual embeddings for `VisualAsset`s (image-level and region-level where supported)
* join visual embeddings to policy + spatial context via cross-modal retrieval
* surface results as evidence cards (precedent analogues), not as recommendations

### 3.7 Two-phase visual semantics (asset → region)
Required pass ordering for planner-legible semantics:
* **Pass A — Asset facts**: classify asset type/subtype and extract canonical/global cues (north arrow, scale bar, legend, etc.).
* **Pass B — Segmentation**: generate region masks + crops for local evidence targeting.
* **Pass C — Region assertions**: emit atomic, typed assertions per region with evidence anchors.
* **Pass D — Embeddings**: embed asset summaries and region assertions for retrieval.

Traceability rule:
* Assertions MUST carry region evidence anchors (region id + evidence refs); fall back to asset evidence only when no region match exists.

## 4) Registration and overlays (plan ↔ world / camera ↔ world)
Registration is the bridge between “plan text” and “physical consequences”.

Minimum:
* raster plan ↔ world transforms with uncertainty (`ingest/PLAN_REALITY_SLICE_B_SPEC.md`)
* overlay artefacts produced and storable (`render/MAP_OVERLAY_SPEC.md`)

Optional (advanced):
* camera pose estimation for viewpoint‑anchored overlays (photomontage reasoning), always caveated.

## 5) Provenance and traceability
* Every model/tool call is logged as `ToolRun`.
* Any derived image/overlay is stored as an artefact and referenced via `EvidenceRef`.
* Output verbosity is controlled at the UI layer (summary/inspect/forensic); no deterministic replay requirement.
