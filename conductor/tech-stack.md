# Technology Stack

## Core Stack
- **Language:** Python 3.x (Back-end), TypeScript (Front-end)
- **Frameworks:**
  - **Back-end:** FastAPI, LangGraph, LangChain, Celery
  - **Front-end:** React (with Vite, Tailwind CSS, Radix UI)
- **Database:** PostgreSQL 16+ (using Psycopg3) with PostGIS
- **Messaging/Task Queue:** Redis, Celery
- **Object Storage:** MinIO (S3-compatible)
- **Infrastructure:** Docker & Docker Compose (OSS Profile)

## AI & Data Processing (OSS Edition)
- **LLM Serving:** vLLM (serving `openai/gpt-oss-20b`)
- **VLM Serving:** vLLM (serving `nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8`)
- **Embeddings:** vLLM (serving `Qwen/Qwen3-Embedding-8B`)
- **Multimodal Embeddings:** vLLM (serving `nomic-ai/colnomic-embed-multimodal-7b`)
- **Reranker:** Text Embeddings Inference (serving `Qwen/Qwen3-Reranker-4B`)
- **Document Parsing:** Docling (OSS DocParseProvider)
- **Computer Vision:**
  - **Segmentation:** SAM2 (Segment Anything Model 2)
  - **Vectorization:** Custom Raster-to-Vector tools
- **Web Automation:** Playwright
- **Model Supervision:** TPA Model Supervisor (manages GPU exclusivity)

## Observability & Testing
- **Tracing/Metrics:** Arize Phoenix (OTEL)
- **End-to-End Testing:** Playwright (UAT Runner)
