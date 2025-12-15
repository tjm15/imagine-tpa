# Provider Interfaces

This document defines the strict interfaces that all providers must implement.

## Interfaces
* `BlobStoreProvider`: put, get, delete blobs.
* `CanonicalDBProvider`: execute SQL, manage transaction.
* `RetrievalProvider`: search (hybrid), index documents.
* `DocParseProvider`: parse document to structured format.
* `EmbeddingProvider`: embed text/image.
* `LLMProvider`: completion, chat (constrained).
* `VLMProvider`: chat with images.
* `SegmentationProvider`: segment image/plan.
* `WorkflowProvider`: orchestrate agent steps.
* `ObservabilityProvider`: log events, metrics, traces.
