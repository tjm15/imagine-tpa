# imagine-tpa

Specification-first scaffold for **The Planner’s Assistant**: a procedurally explainable planning judgement system that logs a replayable reasoning procedure (8-move grammar) and surfaces outputs in a **Dashboard / Digital Case Officer** UI.

**Key specs**
- Constitution: `CONSTITUTION.md`
- Dockerised implementation guide (OSS + Azure profiles): `DOCKERIZED_IMPLEMENTATION_GUIDE.md`
- UI-first build plan: `IMPLEMENTATION_PLAN.md`
- Planner-first workflows: `ux/PLANNER_WORKFLOWS_SPEC.md`
- UI system contracts: `ux/UI_SYSTEM_SPEC.md` and `ux/TRACE_CANVAS_SPEC.md`
- Visuospatial workbench: `ux/VISUOSPATIAL_WORKBENCH_SPEC.md` and `ingest/VISUAL_SPEC.md`
- CULP artefact gating: `culp/PROCESS_MODEL.yaml` and `culp/ARTEFACT_REGISTRY.yaml`
- Capabilities catalogue: `capabilities/CAPABILITIES_CATALOGUE.yaml`
- Grammar (8 moves): `grammar/GRAMMAR.md` and `grammar/MOVE_IO_CATALOGUE.yaml`
- Output schemas: `schemas/`
- Provider profiles (no hybrid runtime): `profiles/azure.yaml` and `profiles/oss.yaml` with contract in `platform/PROVIDER_INTERFACES.md`
- Governance linter: `governance/REASONABLENESS_LINTER_SPEC.md`
- ODP ecosystem interop (PlanX/BOPS/DPR schemas): `integration/DIGITAL_PLANNING_SCHEMAS_INTEROP_SPEC.md`
