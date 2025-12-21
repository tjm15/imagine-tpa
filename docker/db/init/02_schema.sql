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

CREATE TABLE IF NOT EXISTS ingest_jobs (
  id uuid PRIMARY KEY,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  authority_id text NOT NULL,
  plan_cycle_id uuid REFERENCES plan_cycles (id) ON DELETE SET NULL,
  job_type text NOT NULL,
  status text NOT NULL,
  inputs_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  outputs_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL,
  started_at timestamptz,
  completed_at timestamptz,
  error_text text
);

CREATE INDEX IF NOT EXISTS ingest_jobs_status_idx
  ON ingest_jobs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS ingest_jobs_authority_idx
  ON ingest_jobs (authority_id, created_at DESC);

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

CREATE TABLE IF NOT EXISTS parse_bundles (
  id uuid PRIMARY KEY,
  ingest_job_id uuid REFERENCES ingest_jobs (id) ON DELETE SET NULL,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  document_id uuid REFERENCES documents (id) ON DELETE SET NULL,
  schema_version text NOT NULL,
  blob_path text NOT NULL,
  status text NOT NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS parse_bundles_document_idx
  ON parse_bundles (document_id);

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

-- ---------------------------------------------------------------------------
-- Rule packs + workflow state (plan-making FSM + checks)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rule_packs (
  id uuid PRIMARY KEY,
  pack_key text NOT NULL UNIQUE,
  name text NOT NULL,
  jurisdiction text NOT NULL,
  system text NOT NULL,
  current_version_id uuid,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS rule_pack_versions (
  id uuid PRIMARY KEY,
  rule_pack_id uuid NOT NULL REFERENCES rule_packs (id) ON DELETE CASCADE,
  version text NOT NULL,
  effective_from date NOT NULL,
  effective_to date,
  content_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS rule_pack_versions_unique
  ON rule_pack_versions (rule_pack_id, version);

CREATE TABLE IF NOT EXISTS rule_requirements (
  id uuid PRIMARY KEY,
  rule_pack_version_id uuid NOT NULL REFERENCES rule_pack_versions (id) ON DELETE CASCADE,
  requirement_key text NOT NULL,
  requirement_type text NOT NULL,
  culp_stage_id text,
  lifecycle_state_id text,
  params_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  severity text NOT NULL DEFAULT 'hard',
  created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS rule_requirements_pack_idx
  ON rule_requirements (rule_pack_version_id);

CREATE TABLE IF NOT EXISTS rule_checks (
  id uuid PRIMARY KEY,
  rule_pack_version_id uuid NOT NULL REFERENCES rule_pack_versions (id) ON DELETE CASCADE,
  check_key text NOT NULL,
  check_type text NOT NULL,
  from_state_id text,
  to_state_id text,
  params_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  severity text NOT NULL DEFAULT 'hard',
  created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS rule_checks_pack_idx
  ON rule_checks (rule_pack_version_id);

CREATE TABLE IF NOT EXISTS plan_workflow_states (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  rule_pack_version_id uuid NOT NULL REFERENCES rule_pack_versions (id) ON DELETE CASCADE,
  state_id text NOT NULL,
  state_started_at timestamptz NOT NULL,
  state_updated_at timestamptz NOT NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS plan_workflow_states_unique
  ON plan_workflow_states (plan_project_id);

CREATE TABLE IF NOT EXISTS workflow_checklists (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  rule_pack_version_id uuid NOT NULL REFERENCES rule_pack_versions (id) ON DELETE CASCADE,
  state_id text NOT NULL,
  checklist_key text NOT NULL,
  status text NOT NULL,
  completed_at timestamptz,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS workflow_checklists_plan_idx
  ON workflow_checklists (plan_project_id, state_id);

CREATE TABLE IF NOT EXISTS workflow_transitions (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  rule_pack_version_id uuid NOT NULL REFERENCES rule_pack_versions (id) ON DELETE CASCADE,
  from_state_id text NOT NULL,
  to_state_id text NOT NULL,
  transitioned_at timestamptz NOT NULL,
  actor_type text NOT NULL,
  actor_id text,
  notes text,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS workflow_transitions_plan_idx
  ON workflow_transitions (plan_project_id, transitioned_at DESC);

-- ---------------------------------------------------------------------------
-- Timetable + milestones
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS timetables (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  status text NOT NULL,
  public_title text NOT NULL,
  plain_summary text,
  data_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  published_at timestamptz,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS timetables_plan_unique
  ON timetables (plan_project_id);

CREATE TABLE IF NOT EXISTS milestones (
  id uuid PRIMARY KEY,
  timetable_id uuid NOT NULL REFERENCES timetables (id) ON DELETE CASCADE,
  milestone_key text NOT NULL,
  title text NOT NULL,
  due_date date,
  status text NOT NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS milestones_timetable_idx
  ON milestones (timetable_id, due_date);

CREATE TABLE IF NOT EXISTS timetable_reviews (
  id uuid PRIMARY KEY,
  timetable_id uuid NOT NULL REFERENCES timetables (id) ON DELETE CASCADE,
  review_status text NOT NULL,
  reviewed_at timestamptz NOT NULL,
  reviewer text,
  notes text,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- ---------------------------------------------------------------------------
-- Consultation subsystem
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consultations (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  consultation_type text NOT NULL,
  title text NOT NULL,
  status text NOT NULL,
  open_at timestamptz,
  close_at timestamptz,
  channels_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  documents_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS consultations_plan_idx
  ON consultations (plan_project_id, consultation_type);

CREATE TABLE IF NOT EXISTS invitees (
  id uuid PRIMARY KEY,
  consultation_id uuid NOT NULL REFERENCES consultations (id) ON DELETE CASCADE,
  category text NOT NULL,
  name text NOT NULL,
  contact_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  invited_at timestamptz,
  method text,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS invitees_consultation_idx
  ON invitees (consultation_id);

CREATE TABLE IF NOT EXISTS representations (
  id uuid PRIMARY KEY,
  consultation_id uuid NOT NULL REFERENCES consultations (id) ON DELETE CASCADE,
  submitter_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  content_text text,
  tags_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  site_refs_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  policy_refs_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  files_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  submitted_at timestamptz,
  public_redacted_text text,
  status text NOT NULL
);

CREATE INDEX IF NOT EXISTS representations_consultation_idx
  ON representations (consultation_id, submitted_at DESC);

CREATE TABLE IF NOT EXISTS issue_clusters (
  id uuid PRIMARY KEY,
  consultation_id uuid NOT NULL REFERENCES consultations (id) ON DELETE CASCADE,
  title text NOT NULL,
  summary text,
  tags_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  representation_ids_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS consultation_summaries (
  id uuid PRIMARY KEY,
  consultation_id uuid NOT NULL REFERENCES consultations (id) ON DELETE CASCADE,
  summary_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL,
  published_at timestamptz,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

-- ---------------------------------------------------------------------------
-- Evidence graph + traceability
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_items (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  title text NOT NULL,
  evidence_type text NOT NULL,
  publisher text,
  published_date date,
  geography text,
  plan_period text,
  status text NOT NULL,
  source_url text,
  file_hash text,
  storage_path text,
  methodology_summary text,
  quality_flags_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  dependencies_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS evidence_items_plan_idx
  ON evidence_items (plan_project_id, evidence_type);

CREATE TABLE IF NOT EXISTS evidence_gaps (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  gap_type text NOT NULL,
  triggered_by text,
  owner text,
  due_date date,
  risk_level text,
  resolution_evidence_item_id uuid REFERENCES evidence_items (id) ON DELETE SET NULL,
  status text NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS trace_links (
  id uuid PRIMARY KEY,
  from_type text NOT NULL,
  from_id text NOT NULL,
  to_type text NOT NULL,
  to_id text NOT NULL,
  link_type text NOT NULL,
  confidence text,
  notes text,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS trace_links_from_idx
  ON trace_links (from_type, from_id);

CREATE INDEX IF NOT EXISTS trace_links_to_idx
  ON trace_links (to_type, to_id);

-- ---------------------------------------------------------------------------
-- Site selection (Stages 1-4)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS site_categories (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  name text NOT NULL,
  description text,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS site_assessments (
  id uuid PRIMARY KEY,
  site_id uuid NOT NULL REFERENCES sites (id) ON DELETE CASCADE,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  stage text NOT NULL,
  suitability text,
  availability text,
  achievability text,
  notes text,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS site_assessments_plan_idx
  ON site_assessments (plan_project_id, stage);

CREATE TABLE IF NOT EXISTS site_scores (
  id uuid PRIMARY KEY,
  site_assessment_id uuid NOT NULL REFERENCES site_assessments (id) ON DELETE CASCADE,
  dimension text NOT NULL,
  rag text NOT NULL,
  rationale text,
  evidence_refs_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS mitigations (
  id uuid PRIMARY KEY,
  site_assessment_id uuid NOT NULL REFERENCES site_assessments (id) ON DELETE CASCADE,
  description text NOT NULL,
  status text NOT NULL,
  evidence_refs_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS allocation_decisions (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  site_id uuid NOT NULL REFERENCES sites (id) ON DELETE CASCADE,
  decision_status text NOT NULL,
  reason text,
  evidence_refs_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_logs (
  id uuid PRIMARY KEY,
  allocation_decision_id uuid NOT NULL REFERENCES allocation_decisions (id) ON DELETE CASCADE,
  stage text NOT NULL,
  changed_at timestamptz NOT NULL,
  summary text NOT NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS stage4_summary_rows (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  site_id uuid NOT NULL REFERENCES sites (id) ON DELETE CASCADE,
  category text NOT NULL,
  capacity integer,
  phasing text,
  rag_overall text,
  rag_suitability text,
  rag_availability text,
  rag_achievability text,
  justification text,
  deliverable_status text,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

-- ---------------------------------------------------------------------------
-- Gateways + examination + adoption
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gateway_submissions (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  gateway_type text NOT NULL,
  status text NOT NULL,
  submitted_at timestamptz,
  pack_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS gateway_outcomes (
  id uuid PRIMARY KEY,
  gateway_submission_id uuid NOT NULL REFERENCES gateway_submissions (id) ON DELETE CASCADE,
  outcome text NOT NULL,
  findings_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  published_at timestamptz,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS statement_compliance (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  gateway_submission_id uuid REFERENCES gateway_submissions (id) ON DELETE SET NULL,
  statement_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS statement_soundness (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  gateway_submission_id uuid REFERENCES gateway_submissions (id) ON DELETE SET NULL,
  statement_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS readiness_for_exam (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  gateway_submission_id uuid REFERENCES gateway_submissions (id) ON DELETE SET NULL,
  statement_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS examination_events (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  event_type text NOT NULL,
  event_date date NOT NULL,
  details_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS adoption_statements (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  statement_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  published_at timestamptz,
  created_at timestamptz NOT NULL
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

-- ---------------------------------------------------------------------------
-- Publication index (public portal surface)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS publications (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  artefact_key text NOT NULL,
  authored_artefact_id uuid REFERENCES authored_artefacts (id) ON DELETE SET NULL,
  artifact_path text,
  title text NOT NULL,
  status text NOT NULL,
  publish_target text NOT NULL,
  is_immutable boolean NOT NULL DEFAULT false,
  published_at timestamptz,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS publications_plan_idx
  ON publications (plan_project_id, status);

CREATE TABLE IF NOT EXISTS publication_assets (
  id uuid PRIMARY KEY,
  publication_id uuid NOT NULL REFERENCES publications (id) ON DELETE CASCADE,
  asset_path text NOT NULL,
  content_type text NOT NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
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
  received_at timestamptz,
  plan_project_id uuid REFERENCES plan_projects (id) ON DELETE SET NULL,
  plan_cycle_id uuid REFERENCES plan_cycles (id) ON DELETE SET NULL
);

ALTER TABLE applications
  ADD COLUMN IF NOT EXISTS plan_project_id uuid REFERENCES plan_projects (id) ON DELETE SET NULL;

ALTER TABLE applications
  ADD COLUMN IF NOT EXISTS plan_cycle_id uuid REFERENCES plan_cycles (id) ON DELETE SET NULL;

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

CREATE INDEX IF NOT EXISTS applications_plan_project_idx
  ON applications (plan_project_id);

CREATE INDEX IF NOT EXISTS applications_plan_cycle_idx
  ON applications (plan_cycle_id);

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
