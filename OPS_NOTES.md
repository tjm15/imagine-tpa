# Ops Notes

## Ingestion runtime rules
- No timeouts or hard caps for ingestion jobs (pages/bytes/visuals); professionals can submit large packs.
- No auto-retries in ingestion or debug tooling; failures must surface clearly with logs.
- Docparse runs CPU-only; no LLM/VLM usage in docparse.
- Docparse should be comprehensive but non-subjective (omit anything that could be mistaken or judgemental).
- LLM/VLM usage happens in ingest worker(s) only.
- Batch by model class (LLM vs VLM vs embeddings) to avoid GPU model thrash.

## Model/orchestration constraints
- Single-GPU setup: LLM and VLM are mutually exclusive; switching can be slow.
- Embeddings service should host both text (Qwen3) and multimodal (ColNomic) models; keep separate indexes.
- Reranker is allowed and should be wired for text lane precision.
- Do not set LLM/VLM sampling params (temperature/max_tokens/etc.); use model defaults.

## External API / web discovery limits
- External API/web discovery budgets are allowed (rate limits, bytes, pages).
- Ingestion itself must not inherit those caps.

## Debug UI expectations
- /debug remains gated by env flag; should be disabled in production.
- Debug interface must provide manual controls (no auto-retry) and visible, legible logs.
- Include reset/cleanup controls for test runs and stuck queues.

## Storage / MinIO
- MinIO bucket must exist before ingest writes; ensure on startup and/or in storage helper.
- Prefer derived assets only; raw inputs are stored separately as immutable blobs.

## Networking notes
- When running UI dev and API across different hosts (e.g., Tailscale), avoid hardcoding localhost; point Vite proxy to the reachable API host.

## Reasoning traces (ops-facing)
- Reasoning traces are for forensic view only; they do not replace citations.
- Capture levels: summary | inspect | forensic (labeling may evolve, but must remain consistent).
- Output verbosity is not a persisted field; it is a prompt design concern only.
