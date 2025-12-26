## Agent Operating Contract (Index)

This file is now a concise index. Detailed legacy narrative has been moved to `AGENTS_LEGACY_SPEC.md`.

### Objective (non-negotiable)

Build a **procedurally explainable planning judgement system** that:

- Imitates the **8‑move grammar of planning judgement** (not just material considerations).
- Works for **development management (DM)** and **plan‑making / scenario work**.
- Makes reasoning **legible, contestable** via logged procedures and artefacts.
- Produces **conditional suggestions under explicit political framings**.
- Treats external models as **evidence instruments** (logged inputs/outputs + limitations).
- Ships **two non‑hybrid deployment profiles** (Azure vs OSS) behind provider interfaces.

System name: **The Planner's Assistant**.

### Frozen 8‑move grammar (canonical)

1. Framing
2. Issue surfacing
3. Evidence curation
4. Evidence interpretation (incl. plan ↔ reality)
5. Considerations formation (ledger)
6. Weighing & balance
7. Negotiation & alteration
8. Positioning & narration

Source of truth: `grammar/GRAMMAR.md` + `grammar/MOVE_IO_CATALOGUE.yaml` + `schemas/*.schema.json`.

### Core system specs (by area)

- **Constitution & constraints:** `CONSTITUTION.md`
- **CULP process model:** `culp/PROCESS_MODEL.yaml`
- **Provider contract:** `platform/PROVIDER_INTERFACES.md`
- **Provider profiles:** `profiles/azure.yaml`, `profiles/oss.yaml`
- **Canonical DB contract:** `db/DDL_CONTRACT.md`
- **KG schema:** `kg/KG_SCHEMA.md`
- **Provenance standard:** `db/PROVENANCE_STANDARD.md`
- **Ingestion specs:** `ingest/PIPELINE_SPEC.md`, `ingest/DOC_PARSE_SPEC.md`, `ingest/RETRIEVAL_INDEX_SPEC.md`, `ingest/VISUAL_SPEC.md`
- **Plan↔reality overlays:** `ingest/PLAN_REALITY_SLICE_B_SPEC.md`, `render/MAP_OVERLAY_SPEC.md`
- **Agent orchestration:** `agents/GRAMMAR_ORCHESTRATION_SPEC.md`
- **Pre-Application Studio (PESE):** `architecture/PESE_IMPLEMENTATION_PLAN.md`
- **NSIP module:** `architecture/TPA_NSIP_MODULE_SPEC.md`
- **Render pipeline:** `render/FACT_TABLE_SPEC.md`, `render/FIGURE_SPEC.schema.json`, `render/HTML_COMPOSER_SPEC.md`
- **Governance/linting:** `governance/REASONABLENESS_LINTER_SPEC.md`
- **Test contracts:** `tests/INVARIANT_TESTS_SPEC.md`, `tests/FIXTURES_SPEC.md`

### Legacy spec

The full, earlier narrative spec is preserved at `AGENTS_LEGACY_SPEC.md`. Treat it as historical context; the files above are the active sources of truth.
