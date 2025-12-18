# Context Assembly Specification (SOTA Dec 2025)

This spec defines the **Context Assembly** layer: the missing “center” between the evidence substrate (DB + KG + indices) and the grammar agents (LLM/VLM).

It exists to make **multimodal, very‑large‑context reasoning** work **without** letting an LLM “rummage”.

Context Assembly is not a single retrieval query. It is a **planner‑shaped evidence construction procedure**.

---

## 0) Design constraints (non‑negotiable)

1. **Procedural explainability**: Context Assembly must emit logged artefacts, not vibes.
   - Every retrieval, traversal, filter, rerank, caption, crop, overlay, or instrument run is a `ToolRun`.
   - Every inclusion/omission is explicit (Move 3 output + deliberate omissions).
2. **Evidence atoms only**: Context Assembly surfaces **evidence atoms**, not conclusions.
   - Interpretations belong to Move 4.
3. **No hybrid runtime**: Context Assembly operates entirely within the active provider profile.
4. **Multimodal first**: “Policy + maps + plans + photos” are equal citizens in the pack.
5. **Budgeted context**: Even with 128k+ context windows, we must:
   - control token budgets per agent/move,
   - prefer structured packs + expandable drilldowns over dumping everything.

---

## 1) What Context Assembly produces

Context Assembly produces **planner‑native packs** that downstream agents can reason over and the UI can display.

### 1.1 `CuratedEvidenceSet` (Move 3 output)
* Evidence atoms (text/spatial/visual/instrument/user)
* Evidence-by-issue mapping
* Deliberate omissions (what was not pulled and why)
* Tool requests (what evidence is still missing and which instruments/tools could fill it)

Schema: `schemas/CuratedEvidenceSet.schema.json`.

### 1.2 Context packs (internal, UI-ready)
Not a schema freeze yet, but conceptually:
* `policy_pack` (clauses + cross‑refs + weight/status metadata)
* `spatial_pack` (site fingerprints, constraints, networks, key metrics)
* `visual_pack` (plans/photos/overlays + region proposals + captions)
* `precedent_pack` (appeal decisions / committee reports / similar cases)
* `consultation_pack` (clustered themes + representative quotes)

These packs are derived from evidence atoms and are rendered as **Evidence Cards / Evidence Scenes**.

---

## 2) Retrieval is not enough: the “Evidence Lattice”

Context Assembly treats the substrate as an **evidence lattice**:

* **Nodes**: `Chunk`, `PolicyClause`, `SpatialFeature`, `VisualAsset`, `SegmentationMask`, `ProjectionArtifact`, `InstrumentOutput`, …
* **Edges**: planner-shaped links (`CITES`, `MENTIONS`, `INTERSECTS`, `HAS_VISUAL_EVIDENCE`, `DERIVES_OVERLAY`, …).

The goal is to build a **RunGraph slice** that is:
* relevant to the scenario × framing,
* diverse across modalities,
* small enough to reason over,
* expandable by explicit tool calls.

---

## 3) The Context Assembly pipeline (per move, per tab)

Given a `Scenario × Political Framing` tab, Context Assembly runs:

### Step A — Build a `RetrievalFrame`
Inputs:
* `RunContext` (authority, plan cycle, stage)
* scenario state vector (spatial strategy parameters)
* political framing preset
* current move type (Move 2/3/4 need different packs)
* token/time budgets

Outputs:
* a structured retrieval frame (logged into `ToolRun.inputs_logged`)
* modality needs (text/spatial/visual) and filters (status/effective dates)

### Step B — Candidate generation (per modality)
Run separate candidate generators:
* **Text**: FTS + dense embeddings + RRF merge + cross‑encoder rerank (Qwen3‑Reranker‑4B).
* **Spatial**: PostGIS queries + precomputed site fingerprints + constraint/network traversals.
* **Visual**: visual captions + embeddings + region‑level features (from SAM2/VLM) when needed.
* **Precedent/consultation**: same hybrid logic, different indices/filters.

Each generator emits:
* candidate list (with scores),
* provenance (`ToolRun`),
* limitations.

### Step C — KG expansion (controlled multi-hop)
Starting from anchors (scenario, authority, key policies, key spatial triggers), expand the lattice:
* bounded hop count and node budget,
* typed edge filters,
* stop conditions (coverage achieved / budget exhausted).

This is how the system supports “multi-hop” relevance without hallucination.

### Step D — Selection (diversity + counter-evidence)
Select atoms into `CuratedEvidenceSet` with:
* diversity constraints (don’t return 10 near-duplicate chunks),
* coverage targets by issue,
* explicit inclusion of plausible countervailing evidence where available.

Selection should be deterministic given the candidate sets (except where an LLM is explicitly invoked and logged).

### Step E — Pack for downstream agents
Produce move‑specific packs:
* Move 2 (Issue surfacing): broad, high‑recall, lightweight packs.
* Move 3 (Evidence curation): evidence atoms + omission ledger + tool requests.
* Move 4 (Interpretation): tighter, higher‑precision packs plus any required visuals/overlays.

Packs are not prose. They are structured inputs that LLM/VLM agents can reason over, with citations by construction.

---

## 4) Multimodal specifics (visuospatial judgement)

### 4.1 Visual evidence atoms
Visual evidence atoms are produced from:
* `VisualAsset` (plan image, photo, photomontage),
* optional region proposals (SAM2 masks),
* optional VLM descriptions (caption + feature extraction),
* optional plan↔reality registration artefacts (Slice B).

The key is that the VLM is used as an **instrument**:
* input crop(s) + prompts are logged,
* outputs are stored,
* limitations are carried into interpretations and sheets.

### 4.2 Evidence Scenes (planner-native)
Context Assembly should increasingly prefer **Evidence Scenes**:
* a map snapshot,
* an overlay (if present),
* a relevant plan crop,
* a small set of linked policy clauses/chunks,
* any instrument outputs.

This matches how planners actually reason (“looking at the same place through multiple lenses”).

---

## 5) Agentic GIS & tool use (upstream filtering, not magic)

Context Assembly supports agentic GIS by:
* precomputing fingerprints (Slice C) so most queries are cheap lookups,
* emitting `ToolRequest[]` when instruments are needed (Slice D),
* narrowing tool scope (buffers/areas/time horizons) before any expensive run.

LLMs propose tool requests; tools execute deterministically and are logged.

---

## 6) SOTA component mapping (Dec 2025 stance)

OSS profile:
* **Embeddings**: `Qwen/Qwen3-Embedding-*`
* **Reranking**: `Qwen/Qwen3-Reranker-4B` (cross-encoder)
* **VLM**: `Qwen3‑VL`
* **Segmentation**: `SAM 2`
* **Serving**: `vLLM` (LLM/VLM), TEI (embeddings/reranking)
* **Orchestration**: `LangGraph 1.0`

Azure profile swaps in Azure AI Search + Document Intelligence + Azure OpenAI.
