-- Canonical schema bootstrap (idempotent-ish for greenfield dev).
-- This implements the table shapes in `db/DDL_CONTRACT.md`.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP TABLE IF EXISTS policy_clause_embeddings;
DROP TABLE IF EXISTS policy_clauses;
DROP TABLE IF EXISTS policies;
DROP TABLE IF EXISTS chunk_embeddings;

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

CREATE TABLE IF NOT EXISTS ingest_runs (
  id uuid PRIMARY KEY,
  ingest_batch_id uuid NOT NULL REFERENCES ingest_batches (id) ON DELETE CASCADE,
  authority_id text,
  plan_cycle_id uuid REFERENCES plan_cycles (id) ON DELETE SET NULL,
  pipeline_version text,
  model_ids_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  prompt_hashes_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL,
  started_at timestamptz NOT NULL,
  ended_at timestamptz,
  inputs_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  outputs_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_text text
);

CREATE INDEX IF NOT EXISTS ingest_runs_batch_idx
  ON ingest_runs (ingest_batch_id, started_at DESC);

CREATE INDEX IF NOT EXISTS ingest_runs_plan_cycle_idx
  ON ingest_runs (plan_cycle_id, started_at DESC);

CREATE INDEX IF NOT EXISTS ingest_runs_status_idx
  ON ingest_runs (status, started_at DESC);

CREATE TABLE IF NOT EXISTS ingest_run_aliases (
  id uuid PRIMARY KEY,
  scope_type text NOT NULL,
  scope_key text NOT NULL,
  alias text NOT NULL,
  run_id uuid NOT NULL REFERENCES ingest_runs (id) ON DELETE CASCADE,
  set_at timestamptz NOT NULL,
  set_by text,
  notes text
);

CREATE UNIQUE INDEX IF NOT EXISTS ingest_run_aliases_unique
  ON ingest_run_aliases (scope_type, scope_key, alias);

CREATE INDEX IF NOT EXISTS ingest_run_aliases_run_idx
  ON ingest_run_aliases (run_id);

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

CREATE TABLE IF NOT EXISTS ingest_run_steps (
  id uuid PRIMARY KEY,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE CASCADE,
  run_id uuid REFERENCES ingest_runs (id) ON DELETE CASCADE,
  step_name text NOT NULL,
  status text NOT NULL,
  started_at timestamptz,
  ended_at timestamptz,
  inputs_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  outputs_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_text text
);

DROP INDEX IF EXISTS ingest_run_steps_unique;

CREATE UNIQUE INDEX IF NOT EXISTS ingest_run_steps_unique
  ON ingest_run_steps (run_id, step_name);

CREATE INDEX IF NOT EXISTS ingest_run_steps_status_idx
  ON ingest_run_steps (status, started_at DESC);

ALTER TABLE ingest_run_steps
  ALTER COLUMN ingest_batch_id DROP NOT NULL;

ALTER TABLE ingest_run_steps
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE CASCADE;

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
  blob_path text NOT NULL,
  raw_blob_path text,
  raw_sha256 text,
  raw_bytes bigint,
  raw_content_type text,
  raw_source_uri text,
  raw_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL
);

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS raw_blob_path text;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS raw_sha256 text;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS raw_bytes bigint;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS raw_content_type text;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS raw_source_uri text;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS raw_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS documents_authority_id_idx
  ON documents (authority_id);

CREATE INDEX IF NOT EXISTS documents_plan_cycle_idx
  ON documents (plan_cycle_id);

CREATE INDEX IF NOT EXISTS documents_raw_sha_idx
  ON documents (raw_sha256);

CREATE TABLE IF NOT EXISTS pages (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
  page_number integer NOT NULL,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL,
  render_blob_path text,
  render_format text,
  render_dpi integer,
  render_width integer,
  render_height integer,
  render_tier text,
  render_reason text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE pages
  ADD COLUMN IF NOT EXISTS ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL;

ALTER TABLE pages
  ADD COLUMN IF NOT EXISTS source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL;

ALTER TABLE pages
  ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE pages
  ADD COLUMN IF NOT EXISTS render_blob_path text;

ALTER TABLE pages
  ADD COLUMN IF NOT EXISTS render_format text;

ALTER TABLE pages
  ADD COLUMN IF NOT EXISTS render_dpi integer;

ALTER TABLE pages
  ADD COLUMN IF NOT EXISTS render_width integer;

ALTER TABLE pages
  ADD COLUMN IF NOT EXISTS render_height integer;

ALTER TABLE pages
  ADD COLUMN IF NOT EXISTS render_tier text;

ALTER TABLE pages
  ADD COLUMN IF NOT EXISTS render_reason text;

CREATE UNIQUE INDEX IF NOT EXISTS pages_document_page_unique
  ON pages (document_id, page_number);

CREATE TABLE IF NOT EXISTS chunks (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
  page_number integer,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL,
  text text NOT NULL,
  bbox jsonb,
  bbox_quality text,
  type text,
  section_path text,
  span_start integer,
  span_end integer,
  span_quality text,
  evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL;

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL;

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS bbox jsonb;

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS bbox_quality text;

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS type text;

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS section_path text;

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS span_start integer;

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS span_end integer;

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS span_quality text;

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL;

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS chunks_document_id_idx
  ON chunks (document_id);

CREATE TABLE IF NOT EXISTS layout_blocks (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
  page_number integer NOT NULL,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL,
  block_id text NOT NULL,
  block_type text NOT NULL,
  text text NOT NULL,
  bbox jsonb,
  bbox_quality text,
  section_path text,
  span_start integer,
  span_end integer,
  span_quality text,
  evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS layout_blocks_document_block_unique
  ON layout_blocks (document_id, block_id);

CREATE INDEX IF NOT EXISTS layout_blocks_document_idx
  ON layout_blocks (document_id);

CREATE TABLE IF NOT EXISTS document_tables (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
  page_number integer NOT NULL,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL,
  table_id text NOT NULL,
  bbox jsonb,
  bbox_quality text,
  rows_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS document_tables_document_table_unique
  ON document_tables (document_id, table_id);

CREATE INDEX IF NOT EXISTS document_tables_document_idx
  ON document_tables (document_id);

CREATE TABLE IF NOT EXISTS vector_paths (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
  page_number integer NOT NULL,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL,
  path_id text NOT NULL,
  path_type text NOT NULL,
  geometry_jsonb jsonb,
  bbox jsonb,
  bbox_quality text,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS vector_paths_document_path_unique
  ON vector_paths (document_id, path_id);

CREATE INDEX IF NOT EXISTS vector_paths_document_idx
  ON vector_paths (document_id);

-- Retrieval vectors for units (pgvector; OSS RetrievalProvider backend).
-- Dimension is intentionally not fixed here to support swapping embedding models.
CREATE TABLE IF NOT EXISTS unit_embeddings (
  id uuid PRIMARY KEY,
  unit_type text NOT NULL,
  unit_id uuid NOT NULL,
  embedding vector NOT NULL,
  embedding_model_id text NOT NULL,
  embedding_dim integer,
  created_at timestamptz NOT NULL,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS unit_embeddings_unique
  ON unit_embeddings (unit_type, unit_id, embedding_model_id);

CREATE INDEX IF NOT EXISTS unit_embeddings_model_idx
  ON unit_embeddings (embedding_model_id);

CREATE INDEX IF NOT EXISTS unit_embeddings_unit_type_idx
  ON unit_embeddings (unit_type);

CREATE TABLE IF NOT EXISTS visual_assets (
  id uuid PRIMARY KEY,
  document_id uuid REFERENCES documents (id) ON DELETE SET NULL,
  page_number integer,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL,
  asset_type text NOT NULL,
  blob_path text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT NOW(),
  updated_at timestamptz NOT NULL DEFAULT NOW()
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

ALTER TABLE visual_assets
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT NOW();

ALTER TABLE visual_assets
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT NOW();

ALTER TABLE visual_assets
  ADD COLUMN IF NOT EXISTS ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL;

ALTER TABLE visual_assets
  ADD COLUMN IF NOT EXISTS source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL;

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
  run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL,
  label text,
  prompt text,
  mask_artifact_path text NOT NULL,
  mask_rle_jsonb jsonb,
  bbox jsonb,
  bbox_quality text,
  confidence double precision,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS visual_asset_regions (
  id uuid PRIMARY KEY,
  visual_asset_id uuid NOT NULL REFERENCES visual_assets (id) ON DELETE CASCADE,
  run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL,
  region_type text NOT NULL,
  bbox jsonb,
  bbox_quality text,
  mask_id uuid REFERENCES segmentation_masks (id) ON DELETE SET NULL,
  caption_text text,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS visual_asset_regions_asset_idx
  ON visual_asset_regions (visual_asset_id);

CREATE INDEX IF NOT EXISTS visual_asset_regions_run_idx
  ON visual_asset_regions (run_id);

CREATE TABLE IF NOT EXISTS visual_asset_links (
  id uuid PRIMARY KEY,
  visual_asset_id uuid NOT NULL REFERENCES visual_assets (id) ON DELETE CASCADE,
  run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  link_type text NOT NULL,
  evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS visual_asset_links_asset_idx
  ON visual_asset_links (visual_asset_id);

CREATE INDEX IF NOT EXISTS visual_asset_links_target_idx
  ON visual_asset_links (target_type, target_id);

CREATE TABLE IF NOT EXISTS visual_semantic_outputs (
  id uuid PRIMARY KEY,
  visual_asset_id uuid NOT NULL REFERENCES visual_assets (id) ON DELETE CASCADE,
  run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL,
  schema_version text NOT NULL,
  asset_type text,
  asset_subtype text,
  canonical_facts_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  asset_specific_facts_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  assertions_jsonb jsonb NOT NULL DEFAULT '[]'::jsonb,
  agent_findings_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  material_index_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  tool_run_id uuid REFERENCES tool_runs (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS visual_semantic_outputs_asset_idx
  ON visual_semantic_outputs (visual_asset_id);

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

CREATE TABLE IF NOT EXISTS policy_sections (
  id uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
  ingest_batch_id uuid REFERENCES ingest_batches (id) ON DELETE SET NULL,
  source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL,
  policy_code text,
  title text,
  section_path text,
  heading_text text,
  text text NOT NULL,
  page_start integer,
  page_end integer,
  span_start integer,
  span_end integer,
  span_quality text,
  evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS policy_sections_document_idx
  ON policy_sections (document_id);

CREATE TABLE IF NOT EXISTS policy_clauses (
  id uuid PRIMARY KEY,
  policy_section_id uuid NOT NULL REFERENCES policy_sections (id) ON DELETE CASCADE,
  clause_ref text,
  text text NOT NULL,
  page_number integer,
  span_start integer,
  span_end integer,
  span_quality text,
  speech_act_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  subject text,
  object text,
  evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL,
  source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS policy_clauses_section_idx
  ON policy_clauses (policy_section_id);

CREATE TABLE IF NOT EXISTS policy_definitions (
  id uuid PRIMARY KEY,
  policy_section_id uuid REFERENCES policy_sections (id) ON DELETE SET NULL,
  policy_clause_id uuid REFERENCES policy_clauses (id) ON DELETE SET NULL,
  term text NOT NULL,
  definition_text text NOT NULL,
  evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL,
  source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS policy_definitions_term_idx
  ON policy_definitions (term);

CREATE TABLE IF NOT EXISTS policy_targets (
  id uuid PRIMARY KEY,
  policy_section_id uuid REFERENCES policy_sections (id) ON DELETE SET NULL,
  policy_clause_id uuid REFERENCES policy_clauses (id) ON DELETE SET NULL,
  metric text,
  value numeric,
  unit text,
  timeframe text,
  geography_ref text,
  raw_text text,
  evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL,
  source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS policy_monitoring_hooks (
  id uuid PRIMARY KEY,
  policy_section_id uuid REFERENCES policy_sections (id) ON DELETE SET NULL,
  policy_clause_id uuid REFERENCES policy_clauses (id) ON DELETE SET NULL,
  indicator_text text NOT NULL,
  evidence_ref_id uuid REFERENCES evidence_refs (id) ON DELETE SET NULL,
  source_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb
);

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

CREATE TABLE IF NOT EXISTS site_drafts (
  id uuid PRIMARY KEY,
  plan_project_id uuid NOT NULL REFERENCES plan_projects (id) ON DELETE CASCADE,
  geometry_polygon geometry,
  status text NOT NULL,
  metadata_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  expires_at timestamptz,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS site_drafts_plan_idx
  ON site_drafts (plan_project_id, status);

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
  updated_at timestamptz NOT NULL,
  dependency_hash text,
  dependency_snapshot_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb,
  cache_expires_at timestamptz,
  last_run_started_at timestamptz,
  last_run_completed_at timestamptz
);

ALTER TABLE scenario_framing_tabs
  ADD COLUMN IF NOT EXISTS dependency_hash text;

ALTER TABLE scenario_framing_tabs
  ADD COLUMN IF NOT EXISTS dependency_snapshot_jsonb jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE scenario_framing_tabs
  ADD COLUMN IF NOT EXISTS cache_expires_at timestamptz;

ALTER TABLE scenario_framing_tabs
  ADD COLUMN IF NOT EXISTS last_run_started_at timestamptz;

ALTER TABLE scenario_framing_tabs
  ADD COLUMN IF NOT EXISTS last_run_completed_at timestamptz;

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

-- ---------------------------------------------------------------------------
-- Run provenance columns (append-only runs; outputs carry run_id)
-- ---------------------------------------------------------------------------
ALTER TABLE evidence_refs
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE tool_runs
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE parse_bundles
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE pages
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE layout_blocks
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE document_tables
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE vector_paths
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE visual_assets
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE visual_features
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE segmentation_masks
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE segmentation_masks
  ADD COLUMN IF NOT EXISTS mask_rle_jsonb jsonb;

ALTER TABLE segmentation_masks
  ADD COLUMN IF NOT EXISTS bbox jsonb;

ALTER TABLE segmentation_masks
  ADD COLUMN IF NOT EXISTS bbox_quality text;

ALTER TABLE visual_asset_regions
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE visual_asset_links
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE visual_semantic_outputs
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE unit_embeddings
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE policy_sections
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE policy_clauses
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE policy_definitions
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE policy_targets
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE policy_monitoring_hooks
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE frames
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE transforms
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE control_points
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE projection_artifacts
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE kg_edge
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES ingest_runs (id) ON DELETE SET NULL;

ALTER TABLE kg_edge
  ADD COLUMN IF NOT EXISTS edge_class text;

ALTER TABLE kg_edge
  ADD COLUMN IF NOT EXISTS resolve_method text;

COMMIT;
