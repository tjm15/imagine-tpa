# DDL Contract

All state must exist in these tables.

## 1. Canonical Tables
* `plan_cycles` (id, authority_id, plan_name, status, weight_hint, effective_from, effective_to, superseded_by_cycle_id [nullable], is_active, metadata_jsonb, created_at, updated_at)
* `ingest_batches` (id, source_system, authority_id [nullable], plan_cycle_id [nullable], started_at, completed_at [nullable], status, notes [nullable], inputs_jsonb, outputs_jsonb)
* `documents` (id, authority_id, ingest_batch_id [nullable], plan_cycle_id [nullable], document_status [nullable], weight_hint [nullable], effective_from [nullable], effective_to [nullable], is_active, superseded_by_document_id [nullable], confidence_hint [nullable], uncertainty_note [nullable], metadata, blob_path)
* `pages` (id, document_id, page_number, metadata)
* `chunks` (id, document_id, page_number, text, bbox, type, section_path, metadata)
* `chunk_embeddings` (id, chunk_id, embedding, embedding_model_id, created_at, tool_run_id [nullable])
* `visual_assets` (id, document_id, page_number, asset_type, blob_path, metadata)
* `visual_features` (id, visual_asset_id, feature_type, geometry_jsonb, confidence, evidence_ref_id [nullable], tool_run_id [nullable], metadata_jsonb)
* `segmentation_masks` (id, visual_asset_id, label, prompt, mask_artifact_path, confidence, tool_run_id [nullable], created_at)
* `frames` (id, frame_type, epsg [nullable], description [nullable], metadata_jsonb, created_at)
* `transforms` (id, from_frame_id, to_frame_id, method, matrix, matrix_shape, uncertainty_score, control_point_ids_jsonb, tool_run_id [nullable], metadata_jsonb, created_at)
* `control_points` (id, transform_id, src_jsonb, dst_jsonb, residual [nullable], weight [nullable], created_at)
* `projection_artifacts` (id, transform_id, artifact_type, artifact_path, evidence_ref_id [nullable], tool_run_id [nullable], metadata_jsonb, created_at)
* `policies` (id, authority_id, ingest_batch_id [nullable], plan_cycle_id [nullable], policy_status [nullable], policy_weight_hint [nullable], effective_from [nullable], effective_to [nullable], applicability_jsonb, is_active, superseded_by_policy_id [nullable], confidence_hint [nullable], uncertainty_note [nullable], text, overarching_policy_id, metadata)
* `policy_clauses` (id, policy_id, clause_ref, text, metadata)
* `policy_clause_embeddings` (id, policy_clause_id, embedding, embedding_model_id, created_at, tool_run_id [nullable])
* `sites` (id, geometry_polygon, metadata)
* `spatial_features` (id, authority_id [nullable], ingest_batch_id [nullable], type, spatial_scope [nullable], is_active, effective_from [nullable], effective_to [nullable], confidence_hint [nullable], uncertainty_note [nullable], geometry, properties)
* `plan_projects` (id, authority_id, process_model_id, title, status, current_stage_id, metadata_jsonb, created_at, updated_at)
* `culp_artefacts` (id, plan_project_id, culp_stage_id, artefact_key, status, authored_artefact_id [nullable], artifact_path [nullable], evidence_refs_jsonb, produced_by_run_id [nullable], tool_run_ids_jsonb, created_at, updated_at, notes)
* `authored_artefacts` (id, workspace, plan_project_id [nullable], application_id [nullable], culp_stage_id [nullable], artefact_type, title, status, content_format, content_jsonb, exported_artifact_path [nullable], supersedes_artefact_id [nullable], created_by, created_at, updated_at)
* `scenarios` (id, plan_project_id, culp_stage_id, title, summary, state_vector_jsonb, parent_scenario_id [nullable], status, created_by, created_at, updated_at)
* `scenario_sets` (id, plan_project_id, culp_stage_id, political_framing_ids_jsonb, scenario_ids_jsonb, tab_ids_jsonb, selected_tab_id [nullable], selection_rationale [nullable], selected_at [nullable])
* `scenario_framing_tabs` (id, scenario_set_id, scenario_id, political_framing_id, framing_id [nullable], run_id [nullable], status, trajectory_id [nullable], judgement_sheet_ref [nullable], updated_at)
* `trajectories` (id, scenario_id, framing_id, position_statement, explicit_assumptions_jsonb, key_evidence_refs_jsonb, judgement_sheet_jsonb, created_at)
* `scenario_deltas` (id, scenario_set_id, from_scenario_id, to_scenario_id, delta_jsonb, created_at)
* `scenario_evaluations` (id, scenario_id, evaluation_jsonb, created_at)

## 2. Development Management (Casework) Tables
* `applications` (id, authority_id, reference, site_geometry, proposal_metadata, status, received_at)
* `pre_applications` (id, authority_id, reference, site_geometry [nullable], submission_metadata_jsonb, status, received_at)
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
* `move_events` (id, run_id, move_type, sequence, status, created_at, started_at, ended_at, backtracked_from_move_id, backtrack_reason, confidence_hint [nullable], uncertainty_note [nullable], inputs_jsonb, outputs_jsonb, evidence_refs_considered_jsonb, assumptions_introduced_jsonb, uncertainty_remaining_jsonb, tool_run_ids_jsonb)
* `reasoning_evidence_links` (id, run_id [nullable], move_event_id, evidence_ref_id, role, note [nullable], created_at)
* `material_considerations` (id, run_id, move_event_id [nullable], consideration_type, statement, evidence_refs_jsonb, confidence_hint [nullable], uncertainty_note [nullable], created_at)
* `audit_events` (id, timestamp, event_type, actor_type, actor_id, run_id, plan_project_id, culp_stage_id, scenario_id, tool_run_id, payload_jsonb)

## 5. Knowledge Graph Tables (The "Join Fabric")
* `kg_node` (node_id [PK], node_type, props_jsonb, canonical_fk [nullable])
* `kg_edge` (edge_id [PK], src_id [FK], dst_id [FK], edge_type, props_jsonb, evidence_ref_id, tool_run_id)

## 6. Provenance Tables
* `artifacts` (id, type, path)
* `tool_runs` (id, ingest_batch_id [nullable], tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint [nullable], uncertainty_note [nullable])
* `evidence_refs` (id, source_type, source_id, fragment_id)

## 7. Prompt Library Tables (Governance)
Prompts are versioned, auditable governance artefacts (see `agents/PROMPT_LIBRARY_SPEC.md`).
* `prompts` (prompt_id, name, purpose, created_at, created_by)
* `prompt_versions` (prompt_id, prompt_version, template, input_schema_ref, output_schema_ref, created_at, created_by, diff_from_version)

## 8. Snapshot Tables (Audit / diff)
Snapshots are optional but recommended to support “what information was before the decision-maker?” questions.
* `snapshots` (snapshot_id, plan_project_id [nullable], application_id [nullable], run_id [nullable], label, state_jsonb, created_at, created_by [nullable])
* `snapshot_diffs` (diff_id, from_snapshot_id, to_snapshot_id, diff_jsonb, created_at)

## Invariants
* Every `kg_edge` must have a valid `evidence_ref_id` OR `tool_run_id` (provenance is mandatory).
* `kg_node.canonical_fk` links strict graph nodes to rich canonical table rows.
* `plan_cycles` lifecycle: per `authority_id`, at most one active adopted cycle (`status='adopted'`) and at most one active emerging cycle (`status in {'draft','emerging','submitted','examination'}`) at a time (use `is_active=false` + `superseded_by_cycle_id` to retain history).
