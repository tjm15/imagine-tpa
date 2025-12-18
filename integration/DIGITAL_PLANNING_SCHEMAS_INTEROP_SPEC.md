# Digital Planning Data Schemas (OSL) — Interoperability Specification

This spec defines how The Planner’s Assistant interfaces with the **Open Systems Lab (OSL) Digital Planning Data Schemas** used by:
* **Plan✕** (PlanX)
* **Back Office Planning System** (BOPS)
* **Digital Planning Register** (DPR)

Docs UI:
* https://theopensystemslab.github.io/digital-planning-data-schemas-docs/

Source repo:
* https://github.com/theopensystemslab/digital-planning-data-schemas

The objective is interoperability without surrendering the system’s architecture:
* we **normalise into canonical tables** and KG
* we store **raw external payloads as artefacts** with provenance
* we treat schemas as **evidence instruments** (validation + structure), not as decision engines

## 1) Version pinning (no “floating schema”)
Implementations MUST pin the external schema version used for validation and interchange.

Required approach:
1. Pin a specific upstream git ref (commit or tag).
2. Vendor the required JSON schemas into this repo (subset only).
3. Record the pinned ref in `integration/OSL_SCHEMA_SOURCES.yaml`.

This makes connector behaviour replayable and contestable.

Vendored schema subset location (this repo):
* `external_schemas/osl_digital_planning_data_schemas/README.md`

## 2) External schema identifiers we must support (v1 minimum)
The docs UI currently exposes these schema IDs (under a version selector such as `@next`):
* `preApplication`
* `application`
* `enforcement`
* `postSubmissionApplication` (demo)

In v1 we focus on:
* `preApplication` (PlanX inbound)
* `application` (BOPS inbound/outbound; DPR outbound)

`enforcement` is optional unless a selected authority provides it.

## 3) How schema validation is used (connector behaviour)
For any connector that claims OSL-schema interoperability:
1. Fetch external record JSON.
2. Store raw JSON as an `Artifact` and log the fetch as a `ToolRun`.
3. Validate the JSON against the pinned schema:
   * if valid: proceed to normalisation into canonical tables/KG
   * if invalid: store the validation errors as an artefact and mark the run `partial` (do not silently coerce)
4. Record an `ExternalRecordRef` on the canonical object with schema metadata (see `schemas/ExternalRecordRef.schema.json`).

## 4) Canonical mapping (OSL schema → TPA canonical objects)

### 4.1 `application` → canonical `Application`
* Primary canonical object: `schemas/Application.schema.json`
* Persist raw external payload under `proposal_metadata.external.application` (or similar namespaced key).
* Extract:
  - `reference` (stable external id)
  - `received_at` / key dates where present
  - `site_geometry_wkt` when geometry exists (or create a `Site` and link)

### 4.2 `preApplication` → canonical `PreApplication`
* Canonical object: `schemas/PreApplication.schema.json`
* Treat as a first-class DM artefact (enquiry/pre-app), not as an `Application`.
* Link any provided site boundary/point to a `Site` where possible (provenance-backed).

### 4.3 `postSubmissionApplication` → canonical `Application` + revisions (optional)
If a connector provides post-submission data (demo schema):
* map it into:
  - canonical `Application` (current state)
  - `application_revisions` (history)
* never overwrite without recording a revision event (auditability).

### 4.4 `enforcement` → canonical placeholder (optional)
If/when used, create a canonical `EnforcementCase` object/table and store the external payload with provenance.

## 5) Which connectors must implement this

### 5.1 PlanX connector (inbound)
Must accept `preApplication` payloads and normalise into canonical `PreApplication`.

### 5.2 BOPS connector (bidirectional)
Must accept `application` payloads and normalise into canonical `Application`.
Outbound export (if implemented) must emit data conforming to the pinned schema version.

### 5.3 DPR connector (outbound)
Publishes public-facing application/register data.
Outbound export must emit data conforming to the pinned schema version and apply redaction rules where needed.

## 6) Security, privacy, and licensing
OSL schemas describe **shape**, not legal basis.
Implementations must:
* treat application payloads as personal-data-bearing
* apply redaction controls when exporting to a public register (DPR)
* keep provenance so data lineage is inspectable (FOI/JR-friendly)
