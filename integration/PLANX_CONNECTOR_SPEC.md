# PlanX Connector Specification (OSL Schema Interop)


This spec defines the PlanX connector responsibilities in this system.

PlanX interoperability is defined through the Open Systems Lab (OSL) digital planning data schemas:
* Interop spec: `integration/DIGITAL_PLANNING_SCHEMAS_INTEROP_SPEC.md`
* Vendored schemas: `external_schemas/osl_digital_planning_data_schemas/README.md`
  - `preApplication.json` (primary)

## 1) Purpose
Import **pre-application / enquiry** submissions and structured inputs created in PlanX so they become usable evidence in Development Management (and optionally Spatial Strategy baselining signals).

## 2) Inbound object types (minimum)
* OSL `preApplication` payloads

Optional (future):
* documents/attachments referenced by the submission
* structured site boundary geometry (if PlanX supplies it)

## 3) Validation and provenance
For each inbound record:
1. Fetch the JSON payload and store raw as an `Artifact`.
2. Validate against vendored `preApplication.json` (pinned ref in `integration/OSL_SCHEMA_SOURCES.yaml`).
3. Log fetch + validation as `ToolRun` records.
4. Create a canonical `PreApplication` row (`schemas/PreApplication.schema.json`) and attach an `ExternalRecordRef` including:
   * `source_system = planx`
   * `schema_source = osl_digital_planning_data_schemas`
   * `schema_id = preApplication`
   * `schema_ref` pointing to the vendored file path and pinned ref

If validation fails:
* store validation errors as an artefact
* mark the sync as `partial`
* do not silently coerce field shapes

## 4) Canonical mapping (minimum)
Map PlanX `preApplication` into:
* `PreApplication.reference` ← stable external identifier
* `PreApplication.submission_metadata` ← namespaced raw payload (or extracted key fields)
* `PreApplication.site_geometry_wkt` / `site_id` when geometry exists (else null)
* Evidence documents (if available) are ingested via the standard document pipeline and linked.

## 5) UX integration
In DM mode:
* PlanX enquiries appear as inbox items (separate from formal `Application`s).
* “Get a draft” can generate a first response / advice note, but any recommendation requires a full grammar run if it implies judgement.

