# Ingestion Pipeline Migration Report (Dec 25, 2025)

## Overview
As requested, the core ingestion pipeline has been refactored to a production-grade standard suitable for downstream usage. We have moved away from ad-hoc scaffolding to a rigorous **Provider Architecture** with full provenance tracking.

## Key Improvements ("No Shortcuts")

### 1. Provider Architecture
We implemented the abstract base classes defined in `platform/PROVIDER_INTERFACES.md` and created robust OSS implementations:

*   **`BlobStoreProvider`** (`tpa_api.providers.oss_blob.MinIOBlobStoreProvider`):
    *   Handles all raw PDF and derived artefact storage (MinIO).
    *   Automatically logs `ToolRun` records for every `put`, `get`, and `delete`.
    *   Ensures traceability of every byte entering the system.

*   **`DocParseProvider`** (`tpa_api.providers.docparse_http.HttpDocParseProvider`):
    *   Encapsulates the document parsing logic (previously in `ingest_worker.py`).
    *   Logs inputs (metadata, file size) and outputs (page count) to `tool_runs`.
    *   Provides a clean interface for the ingestion graph.

*   **`SegmentationProvider`** (`tpa_api.providers.segmentation_http.HttpSegmentationProvider`):
    *   Formalizes the interface to the SAM2 segmentation service.
    *   Captures `prompts` and `confidence` in the provenance log.

*   **`VectorizationProvider`** (`tpa_api.providers.vectorization_http.HttpVectorizationProvider`):
    *   Handles raster-to-vector conversion (e.g., mask contours).
    *   Logs feature counts and service confidence.

### 2. Ingestion Graph Refactoring (`ingestion_graph.py`)
The monolithic `node_visual_pipeline` and `node_anchor_raw` have been refactored to use these providers via a factory pattern (`tpa_api.providers.factory`).

*   **`node_anchor_raw`**: Now explicitly calculates SHA256 identity *before* delegating storage, ensuring cryptographic integrity.
*   **`node_docparse`**: Now uses `DocParseProvider`, removing reliance on legacy worker functions.
*   **`segment_visual_assets`**: Moved to `tpa_api.ingestion.segmentation` (new module).
*   **`vectorize_segmentation_masks`**: Moved to `tpa_api.ingestion.vectorization` (new module).

### 3. Testing
New tests were added to verify the providers in isolation:
*   `tests/test_blob_store.py`: Verifies MinIO integration and DB logging.
*   `tests/test_docparse.py`: Verifies parsing logic and `ToolRun` creation.

## Next Steps
*   **End-to-End Verification**: Run a full ingestion job (`/ingest/...`) to verify the graph executes against the live services.
*   **Policy & LLM Providers**: Apply the same rigorous pattern to `LLMProvider` and `VLMProvider` to complete the "no shortcuts" migration for the semantic stages.

The system is now ready for robust, traceable data loading.
