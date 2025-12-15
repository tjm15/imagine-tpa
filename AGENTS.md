## System objective and constraints

You are building a **procedurally explainable planning judgement system** that:

* **Imitates the grammar of planning judgement** (not just “material considerations” or final outputs).
* Works for **development management (DM)** *and* **plan‑making / scenario work**.
* Makes reasoning **legible, contestable, and replayable** to planners through **procedural imitation** (explicit moves + logged artefacts), not SHAP/confidence/post‑hoc summaries.
* Produces **conditional suggestions under explicit political framings**:

  > “Under framing X, a reasonable position would be Y, because…”
* **Magpies external models** (DfT Connectivity Tool, CASA QUANT, flood tools, etc.) as **evidence instruments** (logged inputs/outputs + limitations), never as decision engines.
* Has **two complete deployment profiles** with *no hybrid runtime*:

  1. **Fully Azure** (Imagine Cup compliant; uses Microsoft AI services)
  2. **Fully OSS** (self‑hosted open stack)
* Keeps **logic abstracted behind provider interfaces**, so Azure can be swapped for OSS later.

This aligns with the GOV.UK “new system” local plan process (CULP), including notice/timetable/gateways/site selection stages, etc. ([GOV.UK][1])

---

# Part A — The grammar is the spec

## A1) Frozen 8‑move grammar (canonical, non‑negotiable)

1. **Framing**
2. **Issue surfacing**
3. **Evidence curation**
4. **Evidence interpretation** *(includes plan ↔ reality translation)*
5. **Considerations formation** *(ledger)*
6. **Weighing & balance**
7. **Negotiation & alteration**
8. **Positioning & narration**

Everything you build must serve one or more of these moves.

### Procedural imitation contract (what “explainability” means here)

Each move must record:

* what it looked at (evidence atoms, tool outputs)
* how it interpreted them (explicit interpretive artefacts)
* what it produced (structured outputs)
* what assumptions it introduced (explicit ledger entries)
* what uncertainty remains (small list)

This is explainability via **traceable procedure**, not “model confidence”.

---

# Part B — Two complete, non-hybrid pipelines

You will ship **one logical system** with **two provider profiles**. A deployment chooses exactly one profile at runtime.

## B1) Shared logical architecture (provider-agnostic)

**Core services (same in both profiles):**

1. Ingestion service (multi-pass)
2. Canonical store (facts + KG + provenance)
3. Precompute service (fingerprints, indices, caches)
4. Grammar Orchestrator (8-move engine)
5. Tool Runner (spatial, instruments, plan↔reality, renderers)
6. Renderer (HTML infographics → the sheet)
7. CULP Dashboard UI (process navigation + tabbed sheets)
8. Governance/Linter (reasonableness + traceability checks)

**Core idea:**

* Deterministic infrastructure defines **what evidence exists** and records provenance.
* Agentic abduction defines **how to assemble and narrate** within the corridor of reasonableness.

---

## B2) Fully Azure profile (Imagine Cup-ready)

This profile uses Microsoft services end-to-end, including at least two Microsoft AI services, and runs on Azure infrastructure.

### Azure components

* Storage: **Azure Blob Storage**
* Database: **Azure Database for PostgreSQL** (enable PostGIS + pgvector)
* Retrieval/grounding: **Azure AI Search** hybrid retrieval (vector + keyword + RRF merge) ([Microsoft Learn][2])
* Document extraction: **Azure Document Intelligence** (Foundry Tools) for OCR/layout/tables/forms ([Microsoft Azure][3])
* LLM: **Azure OpenAI** (via Foundry Models) for grammar-bound reasoning ([Microsoft Learn][4])
* Compute substrate: **Azure Container Apps** for stateless services and tool runners ([Microsoft Learn][5])
* Orchestration framework (recommended): **Microsoft Agent Framework** / Semantic Kernel lineage for agent development & management in the Microsoft ecosystem ([Microsoft for Developers][6])
* Observability: Application Insights / Azure Monitor; secrets in Key Vault (standard Azure practice)

### Azure “no hybrid” rule

In Azure profile, all critical AI calls go through:

* Azure Document Intelligence (document structure)
* Azure AI Search (retrieval/index)
* Azure OpenAI (reasoning and multimodal interpretation)

You can still run ordinary OSS libraries inside Container Apps, but **no runtime dependency** on self-hosted LLM/VLM/search outside Azure.

---

## B3) Fully OSS profile (self-hosted, SOTA Dec 2025)

This profile is deployable on your own hardware (home GPU or on-prem or any cloud), with open components end-to-end.

### OSS components (SOTA as of Dec 2025)

**Storage**

* S3-compatible: MinIO (or local filesystem in dev)

**Canonical DB**

* PostgreSQL + PostGIS + pgvector (self-host)

**Document processing**

* **Docling** for document parsing/layout/table extraction/OCR pipeline grounding ([docling.ai][7])
  (Optional fallbacks: Tesseract/PaddleOCR; keep those as tools but not required by spec.)

**Embeddings & reranking**

* **Qwen3 Embedding** + reranker family for retrieval/ranking tasks ([Qwen][8])

**Vision (VLM)**

* **Qwen3‑VL** for multimodal understanding, spatial reasoning cues, plan reading ([Qwen][9])

**Segmentation**

* **SAM 2** for promptable segmentation on plans/images/video ([arXiv][10])

**LLM for reasoning**

* **Qwen3** open-weight models for grammar-bound abductive reasoning (dense + MoE options) ([Qwen][11])

**Model serving**

* **vLLM** and/or **SGLang** for high-throughput serving of LLMs/VLMs ([GitHub][12])

**Agent orchestration framework**

* **LangGraph 1.0 / LangChain 1.0** as a durable agent framework for production-grade agent graphs ([LangChain Blog][13])

**No hybrid rule**
In OSS profile there are **no Azure dependencies at runtime** (no Azure Search, no Azure OpenAI, no Azure Document Intelligence). Everything is local/self-hosted.

---

## B4) Provider profile contract (how you prevent “weird hybrid”)

Define a single `ProviderProfile` contract with required providers:

* `BlobStoreProvider`
* `CanonicalDBProvider`
* `RetrievalProvider`
* `DocParseProvider`
* `EmbeddingProvider`
* `LLMProvider`
* `VLMProvider`
* `SegmentationProvider`
* `WorkflowProvider`
* `ObservabilityProvider`

Then ship two concrete configs:

* `profiles/azure.yaml` → Azure providers only
* `profiles/oss.yaml` → OSS providers only

A deployment selects exactly one profile. No mixing at runtime.

---

# Part C — Canonical Knowledge Graph (KG) and data substrate

This is where you stop being “world model generic” and become “planner model computable”.

## C1) Canonical object families (first-class citizens)

### Text & policy

* `Document`, `Page`, `LayoutBlock`, `Chunk`
* `Policy`, `PolicyClause`, `PolicyRef` (cross-refs/supersession)
* `PolicyMapZone` (geographic applicability where available)

### Spatial

* `SpatialDataset`, `SpatialFeature` (constraints, designations, infra)
* `Site`, `Area`, `PlanBoundary`

### Visual & plan-reality

* `VisualAsset` (site plan, elevation, render, aerial, streetview)
* `VisualFeature` (scale bar, north arrow, viewpoint, dimension)
* `SegmentationMask` (SAM2)
* `Frame`, `Transform`, `ControlPoint` (image/plan/world/camera frames)
* `ProjectionArtifact` (overlays proving bidirectionality)

### Procedure & judgement artefacts

* `MoveEvent` (one per grammar move step)
* `Assumption` (ledger)
* `Issue`
* `Interpretation` (what evidence means here, incl plan↔reality)
* `ConsiderationLedgerEntry` (mid-grammar product)
* `WeighingRecord`
* `NegotiationMove`
* `Trajectory` (scenario/position tab)
* `ScenarioJudgementSheet` (renderable output object)

### Provenance

* `Artifact`
* `ToolRun`
* `EvidenceRef`

---

## C2) Graph representation (property graph on Postgres)

Keep everything in Postgres, but expose it as a **typed property graph**:

### Tables

* `kg_node(node_id, node_type, props_jsonb, canonical_fk...)`
* `kg_edge(edge_id, src_id, dst_id, edge_type, props_jsonb, evidence_ref_id, tool_run_id)`
* plus the **canonical tables** (documents, clauses, spatial features, etc.)

You do not replace canonical tables with the KG; the KG is the **join fabric** and traversal accelerator.

### Required edge types (planner-shaped, not generic)

* `CITES` (Chunk → PolicyClause; Clause → Clause)
* `APPLIES_IN` (PolicyClause → PolicyMapZone; Zone → Geometry)
* `MENTIONS` (Chunk → Site/Area/PolicyClause)
* `INTERSECTS` / `WITHIN_DISTANCE` (Site → SpatialFeature) *(precomputed)*
* `HAS_VISUAL_EVIDENCE` (Site → VisualAsset; VisualAsset → VisualFeature)
* `REGISTERED_TO` (VisualAsset → Transform; Transform → Frame)
* `DERIVES_OVERLAY` (Transform → ProjectionArtifact)
* `EVIDENCE_FOR` (EvidenceRef → anything produced)
* `PRODUCED_BY` (Any derived node/edge → ToolRun)
* `PART_OF_MOVE` (Any produced artefact → MoveEvent)
* `ASSUMED_IN` (Assumption → Interpretation/Consideration/Trajectory)
* `SUPPORTS` / `CONTRADICTS` (Interpretation/Consideration ↔ Interpretation/Consideration)

This is enough to support abductive reasoning and replayability without pretending the KG itself “is planning”.

---

# Part D — Agentic context assembly (the missing center)

This is the core: **agentic abductive reasoning over a KG**, producing structured outputs that feed tools and eventually the sheet.

## D1) The run object: a “procedural trace” container

A run creates:

* `RunContext` (anchors + political framing + process stage)
* a **RunGraph** subgraph (hot slice of KG, expandable by tool calls)
* a `MoveEvent[]` stream (procedure log)

The run is replayable because:

* every tool call is logged (`ToolRun`)
* every claim is supported by `EvidenceRef` or marked as `Assumption`

Replay does *not* mean identical prose; it means the **reasoning path is inspectable**.

---

## D2) Evidence atoms vs interpretations vs assumptions (truth-status model)

Every statement used in reasoning must be one of:

* **Evidence atom** (directly sourced: chunk excerpt, spatial fact, overlay image, instrument output)
* **Interpretation** (what an agent infers from evidence, e.g., “this overlay indicates proximity conflict”)
* **Assumption** (explicitly declared, scoped, justified; may be political, practical, or data-gap related)

Your system becomes sane when these are separate objects.

---

## D3) The 8-move agent graph (what each move must output)

Below is a concrete, implementable contract.

### Move 1 — Framing

**Input:** user intent + CULP stage + political framing selection + anchors
**Outputs:**

* `Framing` object:

  * `frame_id`, `frame_title`, `political_framing_id`
  * `purpose` (plain)
  * `scope` (area/sites/time horizon)
  * `decision_audience` (planner/inspector/cabinet/public)
  * `explicit goals`, `explicit constraints`, `non-goals`
* `Assumptions[]` (if any framing assumptions exist)

### Move 2 — Issue surfacing (abductive)

**Input:** RunGraph slice + framing
**Outputs:**

* `Issue[]` (candidate issues) with:

  * `why_material` (plain)
  * `initial evidence hooks` (evidence refs, not prose)
  * `uncertainty` flags
* `IssueMap` (how issues relate: clusters, dependencies, conflicts)

**Mechanism:** abductive. Multiple hypotheses allowed; keep minority issues if plausible.

### Move 3 — Evidence curation

**Input:** issues + KG
**Outputs:**

* `CuratedEvidenceSet`:

  * list of evidence atoms by issue
  * *and* “deliberate omissions” list (what was ignored and why)
* `ToolRequests[]` (to resolve gaps)

In Azure profile, retrieval is via Azure AI Search hybrid queries (keyword + vector + RRF). ([Microsoft Learn][2])
In OSS profile, retrieval is via pgvector + FTS (and optional reranker) using Qwen3 embedding/reranker family. ([Qwen][8])

### Move 4 — Evidence interpretation (includes plan ↔ reality + instruments)

**Input:** curated evidence + tool outputs
**Outputs:**

* `Interpretation[]` objects:

  * claim: “what the evidence means”
  * evidence refs
  * assumptions used
  * limitations text (especially for instruments)
* `PlanRealityInterpretation` objects when relevant:

  * transform confidence, known uncertainty, what overlay shows

This is where Slice B lives: plan↔world registration + overlays are created and interpreted (not just “computed”). ([GOV.UK][14])

### Move 5 — Considerations formation (ledger)

**Input:** interpretations + issues
**Outputs:**

* `ConsiderationLedgerEntry[]`:

  * consideration statement (plain)
  * which policies/tests it engages (links to `PolicyClause`)
  * premises (evidence refs)
  * assumptions
  * mitigations/conditions hooks
  * uncertainty list

Material considerations are produced here, but they do not replace the grammar.

### Move 6 — Weighing & balance

**Input:** ledger + political framing
**Outputs:**

* `WeighingRecord`:

  * which considerations carry weight under framing
  * trade-offs (qualitative, not numeric)
  * what is decisive vs merely relevant
  * how uncertainty affects balance

### Move 7 — Negotiation & alteration

**Input:** weighing + ledger
**Outputs:**

* `NegotiationMove[]`:

  * proposed alterations (policy drafting tweaks / allocation boundaries / mitigation packages / phasing)
  * which considerations they address
  * what evidence would validate them (future data requests)

### Move 8 — Positioning & narration

**Input:** weighing + negotiation + framing
**Outputs:**

* `Trajectory[]` (3–7) **tabs**, each explicitly conditional on a framing:

  * “Under framing X, a reasonable position is…”
  * explicit assumptions and uncertainties
  * evidence card references
* `ScenarioJudgementSheet` (renderable object for each trajectory/tab)

---

## D4) How agents reason over the KG (concrete query primitives)

To make this implementable, define a small set of **graph query primitives** the agents can call (tools, not prompts):

1. `get_policy_stack(area/site, dev_type, timeframe, framing)`
   Returns applicable clauses + cross-refs + status/weight metadata.

2. `get_site_fingerprint(site_id)`
   Returns precomputed intersects/distances + character areas + zones.

3. `get_visual_evidence(site_id)`
   Returns plans/renders/overlays and extracted features.

4. `get_consultation_themes(plan_project_id, stage)`
   Returns clustered themes + representative quotes + salience.

5. `expand_evidence(evidence_id, radius, filters)`
   Traverses KG edges to pull near neighbours.

6. `request_instrument(instrument_id, inputs)`
   Runs an external tool and stores output with limitations.

These are what prevent “LLM rummaging”; the agent explores through typed tools.

---

# Part E — Structured outputs → tools → HTML infographics

Your UI is **infographic-style sheets**, but those sheets are generated by deterministic renderers from structured objects produced by the grammar.

## E1) Output object pipeline (critical separation)

1. **Judgement objects** (JSON)

* Framing, Issues, Interpretations, Ledger, Weighing, Negotiations, Trajectories

2. **Evidence artefacts** (media + data)

* overlay images, map tiles, instrument output tables, charts

3. **Rendered sheet** (HTML)

* a single “Scenario/Judgement Sheet” per tab

The LLM can author text and propose chart narratives, but **rendering is code**.

---

## E2) Toolchain for infographics (both profiles)

### Step 1 — Build fact tables

A deterministic tool constructs “FactTables” from:

* instrument outputs
* site fingerprint metrics
* plan timeline/timetable objects
* consultation salience aggregates

Each row/column has provenance pointers (`EvidenceRef`).

### Step 2 — Generate visual specs (LLM-assisted, bounded)

An agent produces `FigureSpec` objects (e.g., Vega-Lite-like):

* chart type
* fields and encodings
* annotations/captions
* **all references must be to FactTable fields**

### Step 3 — Render charts/maps/overlays (deterministic)

* chart renderer → SVG/PNG
* map renderer → tile/PNG
* overlay renderer → plan↔reality composites

### Step 4 — Compose the HTML sheet

A deterministic HTML renderer (template engine) lays out the sheet sections:

1. What this is about (Framing)
2. What matters here (Issues / Considerations)
3. Evidence cards (policy, map, plan, instrument outputs)
4. Planning balance (plain officer language)
5. Conditional position (explicit framing)
6. Uncertainty (small, honest list)

No internal IDs displayed; click-through reveals evidence cards with plain-language provenance.

---

# Part F — CULP-aligned dashboard (process navigation, not “cockpit”)

You rejected analytics dashboards; that stands. The “dashboard” here is a **process navigator** aligned to the GOV.UK CULP stages, with each stage showing the tabbed sheet(s) produced by the grammar.

## F1) Navigation model (derived from GOV.UK CULP guidance)

### Core timeline skeleton

* **Notice & boundary** (HTML notice, boundary map, downloadable geometry) ([GOV.UK][14])
* **Timetable** (milestones, updates) ([GOV.UK][14])
* **Gateway 1** (self-assessment summary + readiness checker) ([GOV.UK][15])
* **Baselining & place portrait**
* **Vision & ≤10 outcomes**
* **Sites Stage 1–4** (identify, assess, determine allocations, confirm allocations & record decisions) ([GOV.UK][16])
* **Consultation summaries**
* **Gateway 2 / 3** (when guidance/specs exist; placeholders in your system)

This maps directly to the GOV.UK “Create or update a local plan using the new system” collection and related guidance. ([GOV.UK][1])

## F2) What the dashboard actually shows

For each stage:

* status and artefacts required (published / draft / blocked)
* one or more **Scenario/Judgement Sheets** as tabs (3–7)
* evidence cards linked to underlying artefacts

No “compare cockpit”; comparison happens by flipping tabs.

---

# Part G — Specification-of-specifications (what must exist so you don’t drift)

This is the “contract pack” that freezes the system’s shape.

## G1) Constitution & product constraints

* `CONSTITUTION.md`
  (objective, non-goals, UI Freeze 2, political framing requirement, magpie instruments, two profiles, grammar-first)

## G2) Grammar contracts

* `grammar/GRAMMAR.md` (8 moves)
* `grammar/MOVE_IO_CATALOGUE.yaml` (inputs/outputs per move)
* `schemas/MoveEvent.schema.json` (procedure logging)

## G3) CULP process mapping

* `culp/PROCESS_MODEL.yaml`

  * stages, required artefacts per stage, allowed jobs per stage
  * maps to GOV.UK guidance pages (for internal reference) ([GOV.UK][1])
* `ux/DASHBOARD_IA.md` (navigation rules)

## G4) Provider profiles (no hybrid)

* `profiles/azure.yaml`
* `profiles/oss.yaml`
* `platform/PROVIDER_INTERFACES.md` (strict interface list)

## G5) Knowledge graph & canonical schema

* `db/DDL_CONTRACT.md` + migrations
* `kg/KG_SCHEMA.md` (node/edge taxonomy + invariants)
* `db/PROVENANCE_STANDARD.md` (evidence refs and tool_run requirements)

## G6) Ingestion specs (multi-pass, expansive)

* `ingest/PIPELINE_SPEC.md`
* `ingest/PLAN_REALITY_SLICE_B_SPEC.md` (Tier 0 registration + overlays + uncertainty)
* `ingest/DOC_PARSE_SPEC.md`

  * Azure profile: Document Intelligence ([Microsoft Azure][3])
  * OSS profile: Docling ([IBM Research][17])
* `ingest/VISUAL_SPEC.md`

  * OSS: Qwen3‑VL ([Qwen][9])
  * OSS segmentation: SAM2 ([arXiv][10])
* `ingest/RETRIEVAL_INDEX_SPEC.md`

  * Azure: Azure AI Search hybrid search ([Microsoft Learn][2])
  * OSS: pgvector + Qwen3 embeddings ([Qwen][8])
* `ingest/OPENAPI.yaml` (ingestion APIs)

## G7) Agentic reasoning & context assembly

* `agents/GRAMMAR_ORCHESTRATION_SPEC.md` (how the 8 moves run; loops; tool requests)
* `schemas/Framing.schema.json`
* `schemas/Issue.schema.json`
* `schemas/Interpretation.schema.json`
* `schemas/Assumption.schema.json`
* `schemas/ConsiderationLedgerEntry.schema.json`
* `schemas/WeighingRecord.schema.json`
* `schemas/NegotiationMove.schema.json`
* `schemas/Trajectory.schema.json`

## G8) Rendering & infographics

* `schemas/ScenarioJudgementSheet.schema.json` (renderable sheet object)
* `render/FACT_TABLE_SPEC.md`
* `render/FIGURE_SPEC.schema.json`
* `render/HTML_COMPOSER_SPEC.md`
* `render/MAP_OVERLAY_SPEC.md` (plan↔reality overlays)

## G9) Magpie instruments

* `tools/INSTRUMENT_REGISTRY.yaml` (DfT connectivity, flood tools, QUANT, etc.)
* `schemas/InstrumentOutput.schema.json`
* `tools/INSTRUMENT_LIMITATIONS_TEMPLATE.md`

## G10) Reasonableness + traceability enforcement (replace determinism)

* `governance/REASONABLENESS_LINTER_SPEC.md`
  Hard checks:

  * no uncited factual claims
  * assumptions explicit + scoped
  * political framing explicit in positioning
  * instrument limitations always shown
    Soft flags:
  * strained interpretations
  * evidence gaps
  * high transform uncertainty warnings

## G11) Tests (structure, not exact prose)

* `tests/INVARIANT_TESTS_SPEC.md` (grammar completeness, provenance, no leaked IDs)
* `tests/FIXTURES_SPEC.md` (CULP fixture plan + sites + maps + images)
* `tests/REPLAYABILITY_SPEC.md` (reconstruct sheet from MoveEvents + artefacts)

---

# Part H — The “SOTA Dec 2025” stance in one line

* **Azure profile** uses Azure AI Search hybrid retrieval ([Microsoft Learn][2]), Azure Document Intelligence ([Microsoft Azure][3]), and Azure OpenAI (Foundry Models) ([Microsoft Learn][4]) on Azure Container Apps ([Microsoft Learn][5]).
* **OSS profile** uses Docling ([IBM Research][17]), SAM2 ([arXiv][10]), Qwen3‑VL ([Qwen][9]), Qwen3/Qwen3‑Embedding ([Qwen][11]), served via vLLM/SGLang ([GitHub][12]), orchestrated with LangGraph 1.0 ([LangChain Blog][13]).

---

## The next freeze that actually stabilises the system

If you freeze only one thing next, freeze the **grammar move output schemas**, because they tie together:

* agentic KG reasoning,
* tool execution,
* and HTML infographic rendering.

Concretely: `MoveEvent`, `Interpretation`, `Assumption`, `ConsiderationLedgerEntry`, `Trajectory`, and `ScenarioJudgementSheet`.

That gives you a stable mental map and prevents drift while keeping creativity fully inside the corridor of reasonableness.

[1]: https://www.gov.uk/government/collections/create-or-update-a-local-plan-using-the-new-system?utm_source=chatgpt.com "Create or update a local plan using the new system"
[2]: https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview?utm_source=chatgpt.com "Hybrid search using vectors and full text in Azure AI Search"
[3]: https://azure.microsoft.com/en-us/products/ai-foundry/tools/document-intelligence?utm_source=chatgpt.com "Azure Document Intelligence in Foundry Tools"
[4]: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/whats-new?view=foundry-classic&utm_source=chatgpt.com "What's new in Azure OpenAI in Microsoft Foundry Models?"
[5]: https://learn.microsoft.com/en-us/azure/container-apps/?utm_source=chatgpt.com "Azure Container Apps documentation"
[6]: https://devblogs.microsoft.com/semantic-kernel/semantic-kernel-and-microsoft-agent-framework/?utm_source=chatgpt.com "Semantic Kernel and Microsoft Agent Framework"
[7]: https://www.docling.ai/?utm_source=chatgpt.com "Docling - Open Source Document Processing for AI"
[8]: https://qwenlm.github.io/blog/qwen3-embedding/?utm_source=chatgpt.com "Qwen3 Embedding: Advancing Text Embedding and ..."
[9]: https://qwen.ai/blog?from=research.latest-advancements-list&id=99f0335c4ad9ff6153e517418d48535ab6d8afef&utm_source=chatgpt.com "Today, we officially launch the all-new Qwen3-VL ..."
[10]: https://arxiv.org/abs/2408.00714?utm_source=chatgpt.com "SAM 2: Segment Anything in Images and Videos"
[11]: https://qwenlm.github.io/blog/qwen3/?utm_source=chatgpt.com "Qwen3: Think Deeper, Act Faster"
[12]: https://github.com/vllm-project/vllm?utm_source=chatgpt.com "vllm-project/vllm: A high-throughput and memory-efficient ..."
[13]: https://blog.langchain.com/langchain-langgraph-1dot0/?utm_source=chatgpt.com "LangChain and LangGraph Agent Frameworks Reach v1.0 ..."
[14]: https://www.gov.uk/guidance/giving-notice-of-your-plan-making?utm_source=chatgpt.com "Giving notice of your plan-making"
[15]: https://www.gov.uk/guidance/gateway-1-what-you-need-to-do?utm_source=chatgpt.com "Gateway 1: what you need to do"
[16]: https://www.gov.uk/guidance/assessing-sites-for-local-plans-stage-2?utm_source=chatgpt.com "Stage 2: Assessing sites"
[17]: https://research.ibm.com/blog/docling-generative-AI?utm_source=chatgpt.com "IBM is open-sourcing a new toolkit for document conversion"

