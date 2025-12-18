# DPR Connector Specification (OSL Schema Interop)

This spec defines publishing to a Digital Planning Register (DPR).

DPR interoperability is defined through the Open Systems Lab (OSL) digital planning data schemas:
* Interop spec: `integration/DIGITAL_PLANNING_SCHEMAS_INTEROP_SPEC.md`
* Vendored schemas: `external_schemas/osl_digital_planning_data_schemas/README.md`
  - `application.json` (primary export shape)

## 1) Purpose
Publish public-facing register data (applications, decision outcomes, key documents) in a structured, schema-valid form, with explicit redaction controls and auditability.

The DPR connector is treated as an **outbound** integration:
* it exports canonical case state and linked artefacts
* it does not become the system-of-record for internal workflows

## 2) Export object types (minimum)
* OSL `application` payloads representing:
  - application summary fields
  - status/decision outcome where present
  - links to published artefacts (documents, notices)

## 3) Validation, redaction, and provenance
Before export:
1. Build export payload from canonical `Application` + linked artefacts.
2. Apply redaction rules (deployment-configurable):
   * remove personal data where required
   * downgrade precision of geodata where required
3. Validate the final payload against vendored `application.json` pinned in `integration/OSL_SCHEMA_SOURCES.yaml`.

Export is a `ToolRun`:
* inputs: payload hash + selection criteria + redaction policy version
* outputs: request/response metadata + artefact refs

Any publish action is recorded as an `AuditEvent` (who published what, when, on what basis).

## 4) Mapping notes
This system’s authored outputs (reports, notices) are stored as `AuthoredArtefact` and exported as published artefacts (HTML/PDF) linked from the DPR payload where appropriate.

