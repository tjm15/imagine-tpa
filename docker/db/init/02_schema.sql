-- Canonical schema bootstrap (idempotent-ish for greenfield dev).
-- This implements the table shapes in `db/DDL_CONTRACT.md`.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Identity / lifecycle tables (planner-grade audit questions land here)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS plan_cycles (
  id uuid PRIMARY KEY,
  authority_id text NOT NULL,
  plan_name text NOT NULL,
  status text NOT NULL,
  weight_hint text,
  effective_from date,
  effective_to date,
  superseded_by_cycle_id uuid REFERENCES plan_cycles (id) ON DELETE SET NULL,
  is_active boolean NOT NULL DEFAULT true,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS plan_cycles_authority_idx
  ON plan_cycles (authority_id);

-- Common-sense lifecycle constraint:
-- at most one active "emerging" plan cycle (draft/emerging/submitted/examination) per authority.
CREATE UNIQUE INDEX IF NOT EXISTS plan_cycles_unique_active_emerging_per_authority
  ON plan_cycles (authority_id)
  WHERE is_active = true AND status IN ('draft', 'emerging', 'submitted', 'examination');

-- At most one active adopted plan cycle per authority.
CREATE UNIQUE INDEX IF NOT EXISTS plan_cycles_unique_active_adopted_per_authority
  ON plan_cycles (authority_id)
  WHERE is_active = true AND status = 'adopted';

CREATE TABLE IF NOT EXISTS ingest_batches (
  id uuid PRIMARY KEY,
  source_system text NOT NULL,
  authority_id text,
  plan_cycle_id uuid REFERENCES plan_cycles (id) ON DELETE SET NULL,
  started_at timestamptz NOT NULL,
  completed_at timestamptz,
  status text NOT NULL,
  notes text,
  inputs_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  outputs_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ingest_batches_authority_started_idx
  ON ingest_batches (authority_id, started_at DESC);

-- ---------------------------------------------------------------------------
-- Provenance tables (needed by many FK references)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_refs (
  id uuid PRIMARY KEY,
  source_type text NOT NULL,
  source_id text NOT NULL,
  fragment_id text NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS evidence_refs_unique
  ON evidence_refs (source_type, source_id, fragment_id);

CREATE TABLE IF NOT EXISTS tool_runs (
  id uuid PRIMARY KEY,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  tool_name text NOT NULL,
  inputs_logged jsonb NOT NULL DEFAULT '{}'::jsonb,
  outputs_logged jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL,
  started_at timestamptz NOT NULL,
  ended_at timestamptz,
  confidence_hint text,
  uncertainty_note text
);

CREATE INDEX IF NOT EXISTS tool_runs_tool_name_idx
  ON tool_runs (tool_name);

CREATE INDEX IF NOT EXISTS tool_runs_ingest_batch_idx
  ON tool_runs (ingest_batch_id);

CREATE TABLE IF NOT EXISTS artifacts (
  id uuid PRIMARY KEY,
  type text NOT NULL,
  path text NOT NULL
);

-- ---------------------------------------------------------------------------
-- Canonical tables
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
  id uuid PRIMARY KEY,
  authority_id text NOT NULL,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  plan_cycle_id uuid REFERENCES plan_cycles (id) ON DELETE SET NULL,
  document_status text,
  weight_hint text,
  effective_from date,
  effective_to date,
  is_active boolean NOT NULL DEFAULT true,
  superseded_by_document_id uuid REFERENCES documents (id) ON DELETE SET NULL,
  confidence_hint text,
  uncertainty_note text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  blob_path text NOT NULL
);

CREATE INDEX IF NOT EXISTS documents_authority_id_idx
  ON documents (authority_id);

CREATE INDEX IF NOT EXISTS documents_plan_cycle_idx
  ON documents (plan_cycle_id);

CREATE TABLE IF NOT EXISTS pages (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
  page_number integer NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS pages_document_page_unique
  ON pages (document_id, page_number);

CREATE TABLE IF NOT EXISTS chunks (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
  page_number integer,
  text text NOT NULL,
  bbox jsonb,
  type text,
  section_path text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS chunks_document_id_idx
  ON chunks (document_id);

-- Retrieval vectors for chunks (pgvector; OSS RetrievalProvider backend).
-- Dimension is intentionally not fixed here to support swapping embedding models.
CREATE TABLE IF NOT EXISTS chunk_embeddings (
  id uuid PRIMARY KEY,
  chunk_id uuid NOT NULL REFERENCES chunks (id) ON DELETE CASCADE,
  embedding vector NOT NULL,
  embedding_model_id text NOT NULL,
  created_at timestamptz NOT NULL,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS chunk_embeddings_unique
  ON chunk_embeddings (chunk_id, embedding_model_id);

CREATE INDEX IF NOT EXISTS chunk_embeddings_model_idx
  ON chunk_embeddings (embedding_model_id);

CREATE TABLE IF NOT EXISTS visual_assets (
  id uuid PRIMARY KEY,
  document_id uuid REFERENCES documents (id) ON DELETE SET NULL,
  page_number integer,
  asset_type text NOT NULL,
  blob_path text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS visual_assets_document_id_idx
  ON visual_assets (document_id);

CREATE TABLE IF NOT EXISTS visual_features (
  id uuid PRIMARY KEY,
  visual_asset_id uuid NOT NULL REFERENCES visual_assets (id) ON DELETE CASCADE,
  feature_type text NOT NULL,
  geometry_jsonb jsonb,
  confidence double precision,
  evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS visual_features_asset_idx
  ON visual_features (visual_asset_id);

CREATE TABLE IF NOT EXISTS segmentation_masks (
  id uuid PRIMARY KEY,
  visual_asset_id uuid NOT NULL REFERENCES visual_assets (id) ON DELETE CASCADE,
  label text,
  prompt text,
  mask_artifact_path text NOT NULL,
  confidence double precision,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS frames (
  id uuid PRIMARY KEY,
  frame_type text NOT NULL,
  epsg integer,
  description text,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS transforms (
  id uuid PRIMARY KEY,
  from_frame_id uuid NOT NULL REFERENCES frames (id) ON DELETE RESTRICT,
  to_frame_id uuid NOT NULL REFERENCES frames (id) ON DELETE RESTRICT,
  method text NOT NULL,
  matrix jsonb NOT NULL,
  matrix_shape jsonb NOT NULL,
  uncertainty_score double precision,
  control_point_ids_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS control_points (
  id uuid PRIMARY KEY,
  transform_id uuid NOT NULL REFERENCES transforms (id) ON DELETE CASCADE,
  src_jsonb jsonb NOT NULL,
  dst_jsonb jsonb NOT NULL,
  residual double precision,
  weight double precision,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS projection_artifacts (
  id uuid PRIMARY KEY,
  transform_id uuid REFERENCES transforms (id) ON DELETE SET NULL,
  artifact_type text NOT NULL,
  artifact_path text NOT NULL,
  evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS policies (
  id uuid PRIMARY KEY,
  authority_id text NOT NULL,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  plan_cycle_id uuid REFERENCES plan_cycles (id) ON DELETE SET NULL,
  policy_status text,
  policy_weight_hint text,
  effective_from date,
  effective_to date,
  applicability_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_active boolean NOT NULL DEFAULT true,
  superseded_by_policy_id uuid REFERENCES policies (id) ON DELETE SET NULL,
  confidence_hint text,
  uncertainty_note text,
  text text NOT NULL,
  overarching_policy_id uuid REFERENCES policies (id) ON DELETE SET NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS policy_clauses (
  id uuid PRIMARY KEY,
  policy_id uuid NOT NULL REFERENCES policies (id) ON DELETE CASCADE,
  clause_ref text,
  text text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- Retrieval vectors for policy clauses (pgvector; clause-aware retrieval backend).
-- Dimension is intentionally not fixed here to support swapping embedding models.
CREATE TABLE IF NOT EXISTS policy_clause_embeddings (
  id uuid PRIMARY KEY,
  policy_clause_id uuid NOT NULL REFERENCES policy_clauses (id) ON DELETE CASCADE,
  embedding vector NOT NULL,
  embedding_model_id text NOT NULL,
  created_at timestamptz NOT NULL,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS policy_clause_embeddings_unique
  ON policy_clause_embeddings (policy_clause_id, embedding_model_id);

CREATE INDEX IF NOT EXISTS policy_clause_embeddings_model_idx
  ON policy_clause_embeddings (embedding_model_id);

CREATE TABLE IF NOT EXISTS sites (
  id uuid PRIMARY KEY,
  geometry_polygon geometry,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS spatial_features (
  id uuid PRIMARY KEY,
  authority_id text,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  type text NOT NULL,
  spatial_scope text,
  is_active boolean NOT NULL DEFAULT true,
  effective_from date,
  effective_to date,
  confidence_hint text,
  uncertainty_note text,
  geometry geometry,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- Precomputed spatial enrichment for a Site (Slice C).
-- Stored as a logged fingerprint object with provenance (ToolRun) and optional plan-cycle scoping.
CREATE TABLE IF NOT EXISTS site_fingerprints (
  id uuid PRIMARY KEY,
  site_id uuid NOT NULL REFERENCES sites (id) ON DELETE CASCADE,
  plan_cycle_id uuid REFERENCES plan_cycles (id) ON DELETE SET NULL,
  authority_id text,
  fingerprint_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  is_current boolean NOT NULL DEFAULT true,
  superseded_by_fingerprint_id uuid REFERENCES site_fingerprints (id) ON DELETE SET NULL,
  confidence_hint text,
  uncertainty_note text
);

CREATE INDEX IF NOT EXISTS site_fingerprints_site_idx
  ON site_fingerprints (site_id);

CREATE UNIQUE INDEX IF NOT EXISTS site_fingerprints_current_null_plan_unique
  ON site_fingerprints (site_id)
  WHERE is_current = true AND plan_cycle_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS site_fingerprints_current_plan_unique
  ON site_fingerprints (site_id, plan_cycle_id)
  WHERE is_current = true AND plan_cycle_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS plan_projects (
  id uuid PRIMARY KEY,
  authority_id text NOT NULL,
  process_model_id text,
  title text NOT NULL,
  status text NOT NULL,
  current_stage_id text,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS authored_artefacts (
  id uuid PRIMARY KEY,
  workspace text NOT NULL,
  plan_project_id uuid REFERENCES plan_projects (id) ON DELETE SET NULL,
  application_id uuid,
  culp_stage_id text,
  artefact_type text NOT NULL,
  title text NOT NULL,
  status text NOT NULL,
  content_format text NOT NULL,
  content_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  exported_artifact_path text,
  supersedes_artefact_id uuid REFERENCES authored_artefacts (id) ON DELETE SET NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id uuid PRIMARY KEY,
  profile text NOT NULL,
  culp_stage_id text,
  anchors_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS culp_artefacts (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  culp_stage_id text NOT NULL,
  artefact_key text NOT NULL,
  status text NOT NULL,
  authored_artefact_id uuid REFERENCES authored_artefacts (id) ON DELETE SET NULL,
  artifact_path text,
  evidence_refs_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  produced_by_run_id uuid REFERENCES runs (id) ON DELETE SET NULL,
  tool_run_ids_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  notes text
);

CREATE UNIQUE INDEX IF NOT EXISTS culp_artefacts_unique
  ON culp_artefacts (plan_project_id, culp_stage_id, artefact_key);

CREATE TABLE IF NOT EXISTS scenarios (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  culp_stage_id text NOT NULL,
  title text NOT NULL,
  summary text,
  state_vector_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  parent_scenario_id uuid REFERENCES scenarios (id) ON DELETE SET NULL,
  status text NOT NULL,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS scenario_sets (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  culp_stage_id text NOT NULL,
  political_framing_ids_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  scenario_ids_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  tab_ids_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  selected_tab_id uuid,
  selection_rationale text,
  selected_at timestamptz
);

CREATE TABLE IF NOT EXISTS scenario_framing_tabs (
  id uuid PRIMARY KEY,
  scenario_set_id uuid NOT NULL REFERENCES scenario_sets (id) ON DELETE CASCADE,
  scenario_id uuid NOT NULL REFERENCES scenarios (id) ON DELETE CASCADE,
  political_framing_id text NOT NULL,
  framing_id text,
  run_id uuid REFERENCES runs (id) ON DELETE SET NULL,
  status text NOT NULL,
  trajectory_id uuid,
  judgement_sheet_ref text,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS trajectories (
  id uuid PRIMARY KEY,
  scenario_id uuid NOT NULL REFERENCES scenarios (id) ON DELETE CASCADE,
  framing_id text NOT NULL,
  position_statement text NOT NULL,
  explicit_assumptions_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  key_evidence_refs_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  judgement_sheet_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS scenario_deltas (
  id uuid PRIMARY KEY,
  scenario_set_id uuid NOT NULL REFERENCES scenario_sets (id) ON DELETE CASCADE,
  from_scenario_id uuid NOT NULL REFERENCES scenarios (id) ON DELETE CASCADE,
  to_scenario_id uuid NOT NULL REFERENCES scenarios (id) ON DELETE CASCADE,
  delta_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS scenario_evaluations (
  id uuid PRIMARY KEY,
  scenario_id uuid NOT NULL REFERENCES scenarios (id) ON DELETE CASCADE,
  evaluation_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

-- ---------------------------------------------------------------------------
-- Development Management tables
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS applications (
  id uuid PRIMARY KEY,
  authority_id text NOT NULL,
  reference text NOT NULL,
  site_geometry geometry,
  proposal_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL,
  received_at timestamptz
);

CREATE TABLE IF NOT EXISTS pre_applications (
  id uuid PRIMARY KEY,
  authority_id text NOT NULL,
  reference text NOT NULL,
  site_geometry geometry,
  submission_metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL,
  received_at timestamptz
);

CREATE TABLE IF NOT EXISTS application_revisions (
  id uuid PRIMARY KEY,
  application_id uuid NOT NULL REFERENCES applications (id) ON DELETE CASCADE,
  revision_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  received_at timestamptz
);

CREATE TABLE IF NOT EXISTS application_consultations (
  id uuid PRIMARY KEY,
  application_id uuid NOT NULL REFERENCES applications (id) ON DELETE CASCADE,
  consultee text NOT NULL,
  response_text text,
  received_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS conditions (
  id uuid PRIMARY KEY,
  application_id uuid NOT NULL REFERENCES applications (id) ON DELETE CASCADE,
  condition_text text NOT NULL,
  reason_text text,
  status text NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
  id uuid PRIMARY KEY,
  application_id uuid NOT NULL REFERENCES applications (id) ON DELETE CASCADE,
  outcome text NOT NULL,
  decision_date date,
  officer_report_document_id uuid REFERENCES documents (id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------------
-- Monitoring & delivery tables
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monitoring_events (
  id uuid PRIMARY KEY,
  authority_id text NOT NULL,
  event_type text NOT NULL,
  event_date date NOT NULL,
  payload_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS monitoring_timeseries (
  id uuid PRIMARY KEY,
  authority_id text NOT NULL,
  metric_id text NOT NULL,
  period text NOT NULL,
  value double precision,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS adoption_baselines (
  id uuid PRIMARY KEY,
  authority_id text NOT NULL,
  adoption_date date NOT NULL,
  policies_map_ref text,
  metrics_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- ---------------------------------------------------------------------------
-- Procedure tables (replayable judgement)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS move_events (
  id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
  move_type text NOT NULL,
  sequence integer NOT NULL,
  status text NOT NULL,
  created_at timestamptz NOT NULL,
  started_at timestamptz,
  ended_at timestamptz,
  backtracked_from_move_id uuid REFERENCES move_events (id) ON DELETE SET NULL,
  backtrack_reason text,
  confidence_hint text,
  uncertainty_note text,
  inputs_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  outputs_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_refs_considered_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  assumptions_introduced_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  uncertainty_remaining_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  tool_run_ids_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS move_events_run_sequence_unique
  ON move_events (run_id, sequence);

-- Context Assembly spine: persisted retrieval frames that can be refined over a run.
-- These are not conclusions; they are logged plans for what evidence will be sought for a specific move.
CREATE TABLE IF NOT EXISTS retrieval_frames (
  id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
  move_type text NOT NULL,
  version integer NOT NULL,
  is_current boolean NOT NULL DEFAULT true,
  superseded_by_frame_id uuid REFERENCES retrieval_frames (id) ON DELETE SET NULL,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  frame_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS retrieval_frames_current_unique
  ON retrieval_frames (run_id, move_type)
  WHERE is_current = true;

CREATE INDEX IF NOT EXISTS retrieval_frames_run_move_idx
  ON retrieval_frames (run_id, move_type, version DESC);

-- Executable evidence-gathering requests produced by Context Assembly (Move 3) and beyond.
-- These are NOT tool runs; they are queued intentions that become ToolRuns when executed.
CREATE TABLE IF NOT EXISTS tool_requests (
  id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
  move_event_id uuid REFERENCES move_events (id) ON DELETE SET NULL,
  requested_by_move_type text,
  tool_name text NOT NULL,
  instrument_id text,
  purpose text NOT NULL,
  inputs_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  blocking boolean NOT NULL DEFAULT true,
  status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL,
  started_at timestamptz,
  completed_at timestamptz,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  outputs_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_refs_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  error_text text
);

CREATE INDEX IF NOT EXISTS tool_requests_run_idx
  ON tool_requests (run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS tool_requests_status_idx
  ON tool_requests (status);

-- Explicit, legible junction: which evidence was relied on by which reasoning step.
CREATE TABLE IF NOT EXISTS reasoning_evidence_links (
  id uuid PRIMARY KEY,
  run_id uuid REFERENCES runs (id) ON DELETE CASCADE,
  move_event_id uuid NOT NULL REFERENCES move_events (id) ON DELETE CASCADE,
  evidence_ref_id uuid NOT NULL REFERENCES evidence_refs (id) ON DELETE CASCADE,
  role text NOT NULL,
  note text,
  created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS reasoning_evidence_links_move_event_idx
  ON reasoning_evidence_links (move_event_id);

CREATE INDEX IF NOT EXISTS reasoning_evidence_links_evidence_ref_idx
  ON reasoning_evidence_links (evidence_ref_id);

-- Optional planner-law seam: first-class material considerations (beyond emergent JSON).
CREATE TABLE IF NOT EXISTS material_considerations (
  id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES runs (id) ON DELETE CASCADE,
  move_event_id uuid REFERENCES move_events (id) ON DELETE SET NULL,
  consideration_type text NOT NULL,
  statement text NOT NULL,
  evidence_refs_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  confidence_hint text,
  uncertainty_note text,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
  id uuid PRIMARY KEY,
  timestamp timestamptz NOT NULL,
  event_type text NOT NULL,
  actor_type text NOT NULL,
  actor_id text,
  run_id uuid REFERENCES runs (id) ON DELETE SET NULL,
  plan_project_id uuid REFERENCES plan_projects (id) ON DELETE SET NULL,
  culp_stage_id text,
  scenario_id uuid REFERENCES scenarios (id) ON DELETE SET NULL,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  payload_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- ---------------------------------------------------------------------------
-- Knowledge graph tables (join fabric)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kg_node (
  node_id uuid PRIMARY KEY,
  node_type text NOT NULL,
  props_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  canonical_fk uuid
);

CREATE TABLE IF NOT EXISTS kg_edge (
  edge_id uuid PRIMARY KEY,
  src_id uuid NOT NULL REFERENCES kg_node (node_id) ON DELETE CASCADE,
  dst_id uuid NOT NULL REFERENCES kg_node (node_id) ON DELETE CASCADE,
  edge_type text NOT NULL,
  props_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  CONSTRAINT kg_edge_provenance_chk CHECK (evidence_ref_id IS NOT NULL OR tool_run_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS kg_edge_src_idx
  ON kg_edge (src_id);
CREATE INDEX IF NOT EXISTS kg_edge_dst_idx
  ON kg_edge (dst_id);
CREATE INDEX IF NOT EXISTS kg_edge_type_idx
  ON kg_edge (edge_type);

-- ---------------------------------------------------------------------------
-- Prompt library tables (governance)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prompts (
  prompt_id text PRIMARY KEY,
  name text NOT NULL,
  purpose text,
  created_at timestamptz NOT NULL,
  created_by text NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_versions (
  prompt_id text NOT NULL REFERENCES prompts (prompt_id) ON DELETE CASCADE,
  prompt_version integer NOT NULL,
  template text NOT NULL,
  input_schema_ref text,
  output_schema_ref text,
  created_at timestamptz NOT NULL,
  created_by text NOT NULL,
  diff_from_version integer,
  PRIMARY KEY (prompt_id, prompt_version)
);

-- ---------------------------------------------------------------------------
-- Snapshots (audit / diff)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_id uuid PRIMARY KEY,
  plan_project_id uuid REFERENCES plan_projects (id) ON DELETE SET NULL,
  application_id uuid REFERENCES applications (id) ON DELETE SET NULL,
  run_id uuid REFERENCES runs (id) ON DELETE SET NULL,
  label text NOT NULL,
  state_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL,
  created_by text
);

CREATE TABLE IF NOT EXISTS snapshot_diffs (
  diff_id uuid PRIMARY KEY,
  from_snapshot_id uuid NOT NULL REFERENCES snapshots (snapshot_id) ON DELETE CASCADE,
  to_snapshot_id uuid NOT NULL REFERENCES snapshots (snapshot_id) ON DELETE CASCADE,
  diff_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

COMMIT;
