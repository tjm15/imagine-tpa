# PlanIt Connector Specification (Real DM Cases)


This spec defines how the system fetches **real planning applications** from the UK PlanIt API:
`https://www.planit.org.uk/api/`

It is intended for:
* demo / sandbox casework in **Development Management mode**, and
* seeding realistic fixtures for UI/agent development,
while remaining compliant with the system’s core constraints:
* provenance-first (`ToolRun` + citeable `EvidenceRef`)
* no hybrid runtime (AI calls still obey the active profile)
* not a decision engine (imported data is evidence, not judgement)

## 1) Data source characteristics (what PlanIt is)
PlanIt provides a scraped, normalised index of planning applications and planning areas, including:
* core application fields (description, address, dates, decision state)
* point locations (lat/lng) for many applications
* links back to the source planning portal

PlanIt is **rate limited** and the API has hard limits (see PlanIt API docs). Implementations must:
* respect `429` + `Retry-After`
* page results and avoid 5,000-record / 1,000kB output limits
* cache/avoid repeated calls

## 2) Required API endpoints (minimum)

### 2.1 Planning areas discovery
Used to map an authority to PlanIt’s `area_id` / `area_name`.

* `GET /api/areas/json?...`
  * keys (per PlanIt docs): `auth`, `auths`, `area_type`, plus spatial filters (`bbox`, `boundary`, etc.)
  * recommended selection for mapping: `select=area_id,area_name,long_name,gss_code`

Example:
* `/api/areas/json?auths=Brighton&select=area_id,area_name,long_name,gss_code&pg_sz=5&compress=on`

### 2.2 Application search (paged)
Used to fetch lists of applications for an authority.

* `GET /api/applics/json?...`
  * keys (per PlanIt docs): `auth`, `recent`, `changed_start`, `changed_end`, `start_date`, `end_date`, plus paging (`pg_sz`, `page`)

Recommended fields for inbox seeding (keep payload small):
* `select=name,uid,description,address,postcode,app_state,app_type,app_size,start_date,decided_date,last_changed,area_id,area_name,location_x,location_y,link,url,other_fields`
* `compress=on`

### 2.3 Single application details (optional hydration)
Used when an officer opens a case card and we want to refresh details with a single call.

* `GET /planapplic/{name}/json`

Note: PlanIt does not guarantee that attached documents are available via the API; treat `url` as the source-of-truth portal link.

## 3) Authority selection (the “9 authority_packs” constraint)
The connector must only fetch cases for authorities explicitly selected by the deployment.

Two supported mapping modes:

### 3.1 Explicit mapping (recommended for reliability)
Deployment config supplies a mapping:
* `authority_id` → `planit.area_id` (and optionally `planit.area_name`)

This is stable even if names change.

This repo provides a ready mapping for the selected authorities:
* `integration/PLANIT_AUTHORITY_MAP.yaml`

### 3.2 Assisted mapping (optional, requires human confirmation)
If `planit.area_id` is not configured:
1. Look up the authority’s ONS GSS code (or name) from the canonical authority registry (or deployment config).
2. Query `/api/areas/json?area_type=planning&...` (or `auths=...`).
3. Match on `gss_code` where possible.
4. If >1 plausible match, require user confirmation and record an `AuditEvent`.

The resolved mapping must be persisted (canonical DB) so future syncs do not repeat discovery.

### 3.3 Default allowlist source (this repo)
For this repo’s working set, the selected authorities are declared in:
* `authorities/SELECTED_AUTHORITIES.yaml`

Deployments should use that file to seed `authority_allowlist` and (where possible) to assist mapping via GSS codes.

## 4) Sync algorithm (rate-limit safe, incremental)

### 4.1 Initial seed (demo-friendly)
For each selected authority:
* call `/api/applics/json?auth={area_id}&recent={N}&pg_sz={page_size}&page={k}&select=...&compress=on`
* store only the most recent window (e.g. last 30–180 days) for demo/sandbox

### 4.2 Incremental refresh
Use PlanIt’s `last_changed` field to limit updates:
* `changed_start = last_successful_sync_time` (rounded down to day)
* `changed_end = now`

Example:
* `/api/applics/json?auth=43&changed_start=2025-12-01&changed_end=2025-12-18&pg_sz=100&page=1&select=...&compress=on`

### 4.3 Paging + hard limits
The connector must page until `to == total-1` (PlanIt returns `from/to/total`).
If `total > 5000`, the connector must automatically narrow the time window (e.g. split date ranges) rather than attempting to fetch everything.

### 4.4 Error and backoff behaviour
* `429` → respect `Retry-After` and back off; mark the sync run as `partial` if budget exceeded.
* `400` with long query / bad params → shrink page size or narrow query; log error in `ToolRun`.

## 5) Canonical mapping (PlanIt → DM objects)

### 5.1 Canonical `Application` creation
Each PlanIt record becomes (at least) one canonical `Application` (`schemas/Application.schema.json`).

Recommended mapping:
* `authority_id`: internal authority id (selected pack)
* `reference`: PlanIt `uid` if present else PlanIt `name`
* `proposal_metadata.planit`: store the full PlanIt record as JSON for later extraction
* `site_geometry_wkt`: from PlanIt `location` (Point) where present
* `received_at`: `other_fields.date_received` if present, else `start_date`
* `status`: set to `new` on import (internal workflow state is not the same as PlanIt’s status)

### 5.2 Preserve PlanIt status as evidence, not workflow state
Store PlanIt’s:
* `app_state`, `app_type`, `app_size`
* `decision` / `decided_date` (often in `other_fields`)
as part of `proposal_metadata.planit` and/or an evidence card.

The UI may display these as source facts, but internal case workflow remains officer-controlled.

### 5.3 Source references
Applications must record source refs (see `schemas/ExternalRecordRef.schema.json`):
* `source_system = planit`
* `external_type = planapplic`
* `external_id = name` (nationally unique within PlanIt)
* `source_url = link` and `origin_url = url`

## 6) Provenance, artefacts, and EvidenceRefs
Every sync must log:
* a `ToolRun` per HTTP request (inputs = URL + params; outputs = response metadata + stored artefact ref)
* raw JSON responses as artefacts where feasible (or hash if storage constrained)

Evidence refs should be constructible for:
* application description, address, dates, decision state
* link to the source portal

Example evidence ref forms (implementation choice):
* `planit_app::Hackney/2010/2447::field:description`
* `artifact::artifact-123::jsonpath:$.records[0].description`

## 7) Privacy and safety (minimum)
PlanIt data can include personal data (names/addresses). The system must:
* treat PlanIt imports as personal-data-bearing evidence
* allow redaction in rendered/public outputs
* clearly label PlanIt as an external source and link back to the authority portal (`url`)

## 8) UX integration (what this enables)
In **DM mode**:
* Inbox can show real cases for selected authorities.
* Opening a case shows the PlanIt-sourced facts as evidence cards, plus “Get a draft” actions for report sections.
* Trace Canvas shows provenance of any drafted text back to PlanIt evidence cards and policy evidence.

In **Plan/Spatial Strategy mode**:
* PlanIt is optional. It can support monitoring-style signals, but is not required for spatial strategy MVP.
