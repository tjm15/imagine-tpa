# BOPS Connector Specification (OSL Schema Interop)


This spec defines the BOPS connector responsibilities in this system.

BOPS interoperability is defined through the Open Systems Lab (OSL) digital planning data schemas:
* Interop spec: `integration/DIGITAL_PLANNING_SCHEMAS_INTEROP_SPEC.md`
* Vendored schemas: `external_schemas/osl_digital_planning_data_schemas/README.md`
  - `application.json` (primary)
  - `postSubmissionApplication.json` (optional, if BOPS exposes post-submission state/history)

## 1) Purpose
Synchronise Development Management casework with a Back Office Planning System:
* applications
* documents
* consultations/responses
* revisions
* decisions

This connector supports both inbound sync (import) and outbound export (publish/update) where enabled.

## 2) Inbound object types (minimum)
* OSL `application` payloads

Optional (future):
* OSL `postSubmissionApplication` payloads mapped into `application_revisions`

## 3) Validation and provenance
For each inbound record:
1. Fetch payload JSON and store raw as an `Artifact`.
2. Validate against vendored `application.json` (pinned ref in `integration/OSL_SCHEMA_SOURCES.yaml`).
3. Log fetch + validation as `ToolRun` records.
4. Upsert canonical `Application` (`schemas/Application.schema.json`) and attach `ExternalRecordRef` including schema metadata.

Outbound export (if enabled):
* any exported payload must validate against the pinned schema version before sending
* outbound sends are logged as `ToolRun` with request/response artefacts

## 4) Canonical mapping (minimum)
Map OSL `application` into:
* `Application.reference` ← stable external id / reference
* `Application.received_at` ← received/submitted date where available
* `Application.site_geometry_wkt` or `site_id` when geometry exists
* `Application.proposal_metadata` ← namespaced raw payload + extracted key fields (unit counts, floorspace, heights, etc.)

Documents referenced by BOPS must be ingested via the standard document pipeline and linked to the application (canonical + KG `RELIES_ON` edges).

## 5) Workflow triggers (agent-first)
When new/changed applications arrive, the connector may emit a workflow trigger (via `WorkflowProvider`) to:
* run “intake extraction” (facts table + evidence cards)
* run “context analyzer” (site history/constraints)
* prepare a DraftPack for common officer report sections

All triggers must be visible/auditable; do not auto-issue recommendations.

