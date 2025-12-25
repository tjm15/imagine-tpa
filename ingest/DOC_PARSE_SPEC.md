# Document Parsing Specification (ParseBundle v2)


## Strategy
* **OSS Profile**: Docparse emits a ParseBundle v2 using Docling/PyPDF + OCR only. Docparse is **CPU-only** and must not call LLM/VLM services.
* **Azure Profile**: (Not implemented yet; keep the same output contract.)
* **Semantic enrichment happens downstream** in the ingest worker; Docparse provides comprehensive
  structural scaffolding without subjective interpretation.
* **No timeouts or hard caps** are enforced in Docparse for pages/bytes/visuals; operator cancellation only.
* **Parallelism is CPU-only** (safe to use multiple workers on 16 cores).
* **Conditional OCR**: run OCR only when native text confidence is low or pages are image‑heavy; store
  `text_source` + `text_source_reason` on each page and log the decision in `parse_flags`.
  When OCR runs, persist **both** native and OCR text in `text_alternates` with confidences; `pages[].text`
  remains the chosen “best” text.

## Output Contract
Docparse outputs a versioned ParseBundle (schema: `schemas/ParseBundle.schema.json`). This bundle is the only
payload persisted by the ingest worker; it is **provider-agnostic** and carries provenance for traceability.

Minimum fields:
```json
{
  "schema_version": "2.0",
  "bundle_id": "uuid",
  "document": {
    "document_id": "uuid",
    "authority_id": "string",
    "plan_cycle_id": "uuid|null",
    "title": "string",
    "source_url": "string|null",
    "page_count": 12,
    "content_bytes": 1234567
  },
  "pages": [
    {
      "page_number": 1,
      "text": "...",
      "width": 595,
      "height": 842,
      "text_source": "docling_native|ocr",
      "text_source_reason": "native_text_confident|image_heavy|ocr_fallback",
      "text_alternates": {
        "native_text": "...",
        "ocr_text": "...",
        "native_confidence": 0.92,
        "ocr_confidence": 0.41
      },
      "render_blob_path": "page_renders/.../p0001-full.png",
      "render_format": "png",
      "render_dpi": 300,
      "render_width": 2480,
      "render_height": 3508,
      "render_tier": "full",
      "render_reason": "full_res_only"
    }
  ],
  "layout_blocks": [
    {
      "block_id": "b-001",
      "type": "heading|paragraph|bullets|table|caption|other",
      "text": "...",
      "page_number": 1,
      "section_path": "Chapter 4 > Policy H1",
      "bbox": [x0, y0, x1, y1],
      "bbox_quality": "exact|approx|none",
      "evidence_ref": "doc::...::p1-b001"
    }
  ],
  "tables": [
    {
      "table_id": "t-001",
      "page_number": 8,
      "bbox": [x0, y0, x1, y1],
      "bbox_quality": "exact|approx|none",
      "rows": [["Bedrooms", "Spaces"], ["1", "1"]]
    }
  ],
  "visual_assets": [
    {
      "asset_id": "va-001",
      "page_number": 12,
      "asset_type": "unknown",
      "blob_path": "visual_assets/.../va-001.png",
      "bbox": [x0, y0, x1, y1],
      "caption": "Good example of active frontage"
    }
  ],
  "vector_paths": [
    { "path_id": "vp-001", "page_number": 12, "path_type": "map_layer", "geometry": {"type": "MultiLineString"}, "bbox_quality": "approx" }
  ],
  "evidence_refs": [
    {
      "source_doc_id": "uuid",
      "section_ref": "Para 5.12",
      "page_number": 5,
      "snippet_text": "Policy H1 requires...",
      "bbox": [x0, y0, x1, y1],
      "image_ref": "visual_assets/.../va-001.png"
    }
  ],
  "semantic": {
    "policy_headings": [],
    "standard_matrices": [],
    "scope_candidates": [],
    "visual_constraints": [],
    "design_exemplars": []
  },
  "tool_runs": [],
  "limitations": [],
  "tables_unimplemented": false,
  "parse_flags": ["docling_fallback"]
}
```

## Visual Governance Classification
Classification into governance classes happens **in the ingest worker**, not in Docparse:
1. **Governing Geometry** (maps, red-line boundaries) -> DesignationInstance / AllocationSite candidates.
2. **Governing Logic** (diagrams with metrics) -> VisualConstraint / StandardMatrix candidates.
3. **Context & Strategy** (photos/renders, key diagrams) -> DesignExemplar / SpatialStrategyElement candidates.

Docparse may emit a **structural** `asset_type` hint (e.g., image/figure/table_image/unknown) and an
optional `role`. These are provisional hints only. The ingest worker must reclassify with
VLM/OCR + structured prompts and log the outputs as `ToolRun`.

Exemplars are a **subcategory of photos/renders**, not a separate asset type.

## Notes
* ParseBundle is stored in blob storage; only derived assets and bundles are uploaded by Docparse.
  Raw PDFs are stored by the ingest worker **before** Docparse is called.
* `visual_assets` are limited to Docling “figure/image/table‑as‑image” outputs, not every page render.
* `bbox` is best-effort and may be null depending on the source/PDF structure.
* `parse_flags` must include explicit fallback markers (e.g., `docling_fallback`, `docling_errors`) when Docling cannot be used.
* The ingest worker is responsible for persistence, KG wiring, and provenance logging.
* Page renders are always full-resolution (default `TPA_DOCPARSE_RENDER_DPI=300`, `TPA_DOCPARSE_RENDER_FORMAT=png`) and stored in blob storage for explainability overlays.
* `semantic` is present but empty; `policy_headings` is **not populated by Docparse**. The worker uses
  `section_path` and heading hierarchy from `layout_blocks`.
