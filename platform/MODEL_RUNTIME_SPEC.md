# Model Runtime Specification (OSS single-user GPU routing)


This spec pins down how the **OSS profile** runs LLM/VLM/embedding services on a **single machine** with a **single GPU**, without trying to keep all models resident in VRAM simultaneously.

It implements design choice **D3 — a model supervisor**: TPA starts/stops model services on demand, so the GPU is used by the model that is needed *now*.

## 0) Scope and constraints

**Scope**
* OSS profile only (`profiles/oss.yaml`)
* single-user workbench (no multi-tenant scaling)
* local Docker Compose deployment (`docker/compose.oss.yml`)

**Constraints**
* VRAM is the scarce resource; do not assume LLM + VLM can co-reside.
* “Standby in RAM then copy to GPU” is approximated via shared model cache volumes and OS page cache.
* Embeddings may run as a **multi-model service** (text + multimodal) and should stay resident if VRAM allows.

Non-goal: perfect “hot swap” of weights between GPU and RAM (not currently realistic with typical LLM servers).

## 1) Runtime goal

Given a workbench action, TPA must be able to:
* run **LLM** calls when needed (drafting, grammar moves),
* run **VLM** calls when needed (plan/photomontage interpretation),
* run **embeddings** when needed (retrieval),
…without requiring the user to manually manage containers or VRAM.

## 2) Model roles

TPA treats models as roles (not “one mega model”):
* `llm` — OpenAI-compatible text completion/chat (vLLM)
* `vlm` — OpenAI-compatible multimodal chat (vLLM)
* `embeddings` — embedding HTTP service (multi-model: text + multimodal, routed by `model_id`)
* `reranker` — cross-encoder reranker HTTP service (e.g. TEI)

## 3) The Model Supervisor (D3)

### 3.1 Responsibilities
The Model Supervisor is a small control-plane service that:
1. **Ensures** a requested model role is available (started + healthy).
2. **Enforces GPU exclusivity** between `llm` and `vlm` on single-GPU installs:
   - if `vlm` is requested and `llm` is running, stop `llm` first (and vice versa).
3. **Returns a base URL** for the caller to use (e.g. `http://tpa-llm:8000/v1`).
4. Optionally applies **idle shutdown** (stop the inactive GPU model after N minutes).

### 3.2 What the supervisor does NOT do
* It does not “decide” which role to use; callers decide (agents and tools).
* It does not generate planning outputs; it is infrastructure only.
* It does not cross profiles (no Azure/OSS mixing).

### 3.3 API contract (internal)
The minimum internal HTTP contract:
* `POST /ensure` with `{ "role": "llm" | "vlm" | "embeddings" }`
  - returns `{ "role": "...", "base_url": "...", "status": "ready" | "starting" }`
* `POST /stop` with `{ "role": "llm" | "vlm" }` (optional; mostly for debugging)
* `GET /status` returns the running/healthy role(s) and last-use timestamps

## 4) Docker/Compose strategy

### 4.1 Default
* `tpa-embeddings` may run continuously (CPU) because it does not contend for VRAM by default.
* Exactly one of `tpa-llm` or `tpa-vlm` should be running at any time.

If `embeddings`/`reranker` are configured to use the GPU, treat them as GPU roles.
The supervisor may allow `embeddings` + `reranker` to co-reside if VRAM permits, but `llm` and `vlm`
remain mutually exclusive by default.

### 4.3 Multi-model embeddings (dual-lane retrieval)
The embeddings service may host:
* a **text** model (e.g., Qwen3-Embedding-8B) for clause/chunk retrieval, and
* a **multimodal** model (e.g., ColNomic) for page-level visual retrieval.

Requests must provide `model_id` and the service must return which model was used.
Indexes remain separate (text vs visual pages) and are routed at query time.

### 4.2 Shared cache (RAM-friendly behavior)
All model services share a volume:
* `tpa_models:/models` with `HF_HOME=/models/cache`

This allows:
* one-time downloads,
* filesystem caching,
* OS page cache to keep frequently used weights “warm” in RAM.

## 5) Single-user tuning defaults

Because OSS is single-user, model servers should use conservative batching:
* vLLM should default to low concurrency (`--max-num-seqs` small).
* any further tuning (sequence length, kv cache) is a deployment concern, not planning logic.

## 6) Where this hooks into the app

* Providers (`LLMProvider`, `VLMProvider`, `EmbeddingProvider`) may call the supervisor before issuing requests.
* UI “Draft” and visuospatial tools indirectly trigger the right role through the orchestrator/tool runner.

This preserves the core design rule:
* **Agents decide** what tools/models are needed.
* **Infrastructure ensures** they are available.

## 7) Implementation options (and implications)

There are two realistic ways to implement D3 in a Dockerised OSS stack.

### Option 7.1 — In-compose supervisor with Docker Engine access (recommended for “it just works”)
**Mechanism**
* Run `tpa-model-supervisor` as a container that can start/stop `tpa-llm`/`tpa-vlm`.
* Grant it access to the Docker Engine API (typically via `/var/run/docker.sock`).

**Pros**
* Best UX: the workbench can automatically bring up the right model role and enforce “LLM OR VLM, not both”.
* Least planner friction: no “please start the vlm profile” dead ends.
* Lets the UI show “starting model…” states cleanly (preflight can trigger warm starts).

**Cons / risks**
* **Security**: mounting the Docker socket is effectively **root-equivalent access to the host**.
  - If the supervisor is compromised, the host is compromised.
* **Operational coupling**: depends on Docker Engine semantics and stable service/container identity.
* **Profile nuance**: model services must exist (created) for start/stop; if they are excluded by profiles, the supervisor must either:
  - require a one-time `docker compose --profile models create`, or
  - be able to create containers itself (more complex).

**Required mitigations (minimum bar)**
* Do not publish the supervisor port to the host; keep it internal to the Docker network.
* Authenticate API→supervisor calls with a shared secret (or network allowlist).
* Supervisor must only allow start/stop/health checks for an allowlisted set of services (no arbitrary images/commands).
* Prefer a Docker socket proxy that only exposes the minimum endpoints required to start/stop containers.

When this option is used, do not run the stack on an untrusted network or expose it to the public internet.

### Option 7.2 — No Docker Engine access (manual model profiles + predictable degradation)
**Mechanism**
* Keep model services opt-in (`docker compose --profile llm up -d tpa-llm`, etc.).
* If a model is unavailable, the orchestrator/providers return a `ToolRequest` explaining what to start and why.

**Pros**
* Strongest security posture (no privileged control-plane inside the app).
* Simple and portable (works anywhere Compose works).
* Failure modes are explicit and planner-legible (“tool unavailable; start model role X”).

**Cons**
* More user friction: the planner must start/stop LLM/VLM manually.
* Easier to hit VRAM contention by mistake (forgetting to stop one before starting the other).
* Harder to deliver the “frontier AI workbench” feel where navigation triggers preflight automatically.

## 8) Repo implementation (OSS compose)

This repo implements **Option 7.1** as:
* Service: `tpa-model-supervisor` (FastAPI) in `apps/model_supervisor/`
* Compose profile: `models-auto` in `docker/compose.oss.yml`
* API integration: set `TPA_MODEL_SUPERVISOR_URL=http://tpa-model-supervisor:8091` so `tpa-api` ensures roles before calling model endpoints.
