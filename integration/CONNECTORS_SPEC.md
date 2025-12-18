# Integration Layer (Connectors) Specification

The Integration Layer keeps the Assistant’s internal canonical store + KG synchronised with external planning systems and live evidence feeds.

This layer is required to support capabilities such as:
* DM intake + case updates (applications, consultees, revisions)
* Monitoring connectors (completions, appeals, S106/CIL)
* Plan data ingestion (ODP-aligned plan documents and datasets)
* Demo/sandbox case seeding from public aggregators (e.g. UK PlanIt)

## 1) Principles
* **Normalise, don’t mirror**: external schemas are mapped into canonical tables and KG nodes/edges.
* **Event-aware sync**: changes propagate as events (pull/push), logged as `ToolRun`.
* **Provenance first**: every imported record is traceable to a source system + time.
* **No hybrid runtime**: connector implementations must respect the active provider profile (Azure vs OSS) for AI calls and storage.
* **Public data acquisition**: connectors may also pull from public sources and governed web discovery (see `integration/PUBLIC_DATA_SPEC.md`).

## 2) Connector responsibilities
Each connector must:
1. Authenticate and fetch external data (or accept webhooks).
2. Map external objects into canonical schemas.
3. Record provenance (`EvidenceRef` + `ToolRun`).
4. Emit “change events” into the orchestration layer (workflow triggers).

## 3) Registry
Connectors are declared in `integration/CONNECTORS_REGISTRY.yaml` and configured per deployment.

## 4) Minimum connector set (v1)
* `bops` (casework: application status, documents, decision outcomes)
* `planx` (enquiries / site constraint signals where applicable)
* `odp` (plan/policy datasets, design codes, spatial datasets)
* `monitoring_completions` (delivery feeds)
* `monitoring_appeals` (appeal outcomes/overturns)
* `monitoring_s106` (developer contributions)
* `dpr` (publishing to a Digital Planning Register)

Optional (demo / sandbox):
* `planit` (UK PlanIt API application feed; see `integration/PLANIT_CONNECTOR_SPEC.md`)

## 5) External schema interoperability (ODP ecosystem)
PlanX/BOPS/DPR integrations should validate and exchange records using the OSL digital planning data schemas:
* Spec: `integration/DIGITAL_PLANNING_SCHEMAS_INTEROP_SPEC.md`
* Version pinning registry: `integration/OSL_SCHEMA_SOURCES.yaml`
