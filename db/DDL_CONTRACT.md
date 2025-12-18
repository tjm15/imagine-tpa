# DDL Contract

All state must exist in these tables.

## 1. Canonical Tables
* `documents` (id, authority_id, metadata, blob_path)
* `pages` (id, document_id, page_number, metadata)
* `chunks` (id, document_id, page_number, text, bbox, type, section_path, metadata)
* `visual_assets` (id, document_id, page_number, asset_type, blob_path, metadata)
* `policies` (id, authority_id, text, overarching_policy_id, metadata)
* `policy_clauses` (id, policy_id, clause_ref, text, metadata)
* `sites` (id, geometry_polygon, metadata)
* `spatial_features` (id, type, geometry, properties)

## 2. Development Management (Casework) Tables
* `applications` (id, authority_id, reference, site_geometry, proposal_metadata, status, received_at)
* `application_revisions` (id, application_id, revision_metadata, received_at)
* `application_consultations` (id, application_id, consultee, response_text, received_at, metadata)
* `conditions` (id, application_id, condition_text, reason_text, status)
* `decisions` (id, application_id, outcome, decision_date, officer_report_document_id)

## 3. Monitoring & Delivery Tables
* `monitoring_events` (id, authority_id, event_type, event_date, payload_jsonb, provenance)
* `monitoring_timeseries` (id, authority_id, metric_id, period, value, provenance)
* `adoption_baselines` (id, authority_id, adoption_date, policies_map_ref, metrics_jsonb, provenance)

## 4. Procedure Tables (Replayable Judgement)
* `runs` (id, profile, culp_stage_id, anchors_jsonb, created_at)
* `move_events` (id, run_id, move_type, inputs_jsonb, outputs_jsonb, tool_run_ids, created_at)
* `audit_events` (id, timestamp, event_type, actor_type, actor_id, run_id, plan_project_id, culp_stage_id, scenario_id, tool_run_id, payload_jsonb)

## 5. Knowledge Graph Tables (The "Join Fabric")
* `kg_node` (node_id [PK], node_type, props_jsonb, canonical_fk [nullable])
* `kg_edge` (edge_id [PK], src_id [FK], dst_id [FK], edge_type, props_jsonb, evidence_ref_id, tool_run_id)

## 6. Provenance Tables
* `artifacts` (id, type, path)
* `tool_runs` (id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at)
* `evidence_refs` (id, source_type, source_id, fragment_id)

## 7. Prompt Library Tables (Governance)
Prompts are versioned, auditable governance artefacts (see `agents/PROMPT_LIBRARY_SPEC.md`).
* `prompts` (prompt_id, name, purpose, created_at, created_by)
* `prompt_versions` (prompt_id, prompt_version, template, input_schema_ref, output_schema_ref, created_at, created_by, diff_from_version)

## 8. Snapshot Tables (Audit / diff)
Snapshots are optional but recommended to support “what information was before the decision-maker?” questions.
* `snapshots` (snapshot_id, plan_project_id, run_id, label, state_jsonb, created_at)
* `snapshot_diffs` (diff_id, from_snapshot_id, to_snapshot_id, diff_jsonb, created_at)

## Invariants
* Every `kg_edge` must have a valid `evidence_ref_id` OR `tool_run_id` (provenance is mandatory).
* `kg_node.canonical_fk` links strict graph nodes to rich canonical table rows.
