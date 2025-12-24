import json
import logging
import os
from typing import TypedDict, Annotated, List, Dict, Any, Optional
from uuid import UUID

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

# Import existing logic
from tpa_api.ingest_worker import (
    _call_docparse_bundle,
    _load_parse_bundle,
    _persist_pages,
    _persist_layout_blocks,
    _persist_chunks_from_blocks,
    _persist_visual_assets,
    _persist_tool_runs,
    _insert_parse_bundle_record,
    _persist_bundle_evidence_refs,
    _persist_document_tables,
    _persist_vector_paths,
    _persist_visual_features,
    _extract_visual_asset_facts,
    _extract_visual_text_snippets,
    _segment_visual_assets,
    _vectorize_segmentation_masks,
    _extract_visual_region_assertions,
    _auto_georef_visual_assets,
    _extract_document_identity_status,
    _llm_extract_policy_structure,
    _merge_policy_headings,
    _persist_policy_structure,
    _llm_extract_policy_logic_assets,
    _persist_policy_logic_assets,
    _llm_extract_edges,
    _persist_policy_edges,
    _persist_kg_nodes,
    _embed_units,
    _embed_visual_assertions,
    _db_fetch_one,
    _db_execute,
    init_db_pool,
    _start_run_step,
    _finish_run_step
)

# Configuration
logger = logging.getLogger(__name__)
DB_DSN = os.environ.get("TPA_DB_DSN", "postgresql://tpa:tpa@localhost:5432/tpa")

class IngestionState(TypedDict):
    run_id: str
    ingest_batch_id: str
    authority_id: str
    plan_cycle_id: Optional[str]
    document_id: str
    filename: str
    file_bytes: bytes
    doc_metadata: dict
    
    # State tracking
    bundle_path: Optional[str]
    visual_assets_persisted: bool
    policy_structure_persisted: bool
    
    # Internal context
    manifest: dict
    
    # Error handling
    error: Optional[str]

def node_docparse(state: IngestionState) -> IngestionState:
    """Calls DocParse to generate the parse bundle."""
    try:
        _start_run_step(run_id=state['run_id'], ingest_batch_id=state['ingest_batch_id'], step_name="docling_parse", inputs={"filename": state['filename']})
        
        # Check idempotency
        existing = _db_fetch_one("SELECT blob_path FROM parse_bundles WHERE document_id = %s::uuid", (state['document_id'],))
        if existing:
            return {**state, "bundle_path": existing['blob_path']}

        result = _call_docparse_bundle(
            file_bytes=state['file_bytes'],
            filename=state['filename'],
            metadata=state['doc_metadata'],
            ingest_batch_id=state['ingest_batch_id'],
            run_id=state['run_id']
        )
        path = result.get('parse_bundle_path')
        _finish_run_step(run_id=state['run_id'], step_name="docling_parse", status="completed", outputs={"parse_bundle_path": path})
        return {**state, "bundle_path": path}
    except Exception as e:
        _finish_run_step(run_id=state['run_id'], step_name="docling_parse", status="failed", outputs={}, error_text=str(e))
        return {**state, "error": str(e)}

def node_canonical_load(state: IngestionState) -> IngestionState:
    """Persists standard artifacts (pages, blocks, visuals) from the bundle."""
    if state.get('error'): return state
    
    try:
        _start_run_step(run_id=state['run_id'], ingest_batch_id=state['ingest_batch_id'], step_name="canonical_load", inputs={})
        
        # Idempotency check: Do pages exist?
        pages_exist = _db_fetch_one("SELECT count(*) as c FROM pages WHERE document_id = %s::uuid", (state['document_id'],))
        if pages_exist and pages_exist['c'] > 0:
             _finish_run_step(run_id=state['run_id'], step_name="canonical_load", status="completed", outputs={"skipped": True})
             return {**state, "visual_assets_persisted": True}

        bundle = _load_parse_bundle(state['bundle_path'])
        
        # Insert Bundle Record
        _insert_parse_bundle_record(
            ingest_job_id=str(UUID(int=0)), # Hack for now
            ingest_batch_id=state['ingest_batch_id'],
            run_id=state['run_id'],
            document_id=state['document_id'],
            schema_version=bundle.get("schema_version") or "2.0",
            blob_path=state['bundle_path'],
            metadata={}
        )
        
        pages = bundle.get("pages") or []
        _persist_pages(document_id=state['document_id'], ingest_batch_id=state['ingest_batch_id'], run_id=state['run_id'], source_artifact_id=None, pages=pages)
        
        bundle_refs = bundle.get("evidence_refs") or []
        ref_map = _persist_bundle_evidence_refs(run_id=state['run_id'], evidence_refs=bundle_refs)
        
        blocks = bundle.get("layout_blocks") or []
        _persist_layout_blocks(document_id=state['document_id'], ingest_batch_id=state['ingest_batch_id'], run_id=state['run_id'], source_artifact_id=None, pages=pages, blocks=blocks, evidence_ref_map=ref_map)
        
        visual_assets = bundle.get("visual_assets") or []
        _persist_visual_assets(document_id=state['document_id'], ingest_batch_id=state['ingest_batch_id'], run_id=state['run_id'], source_artifact_id=None, visual_assets=visual_assets, evidence_ref_map=ref_map)
        
        _finish_run_step(run_id=state['run_id'], step_name="canonical_load", status="completed", outputs={"pages": len(pages)})
        return {**state, "visual_assets_persisted": True}
        
    except Exception as e:
        _finish_run_step(run_id=state['run_id'], step_name="canonical_load", status="failed", outputs={}, error_text=str(e))
        return {**state, "error": str(e)}

def build_ingestion_graph(checkpointer=None):
    workflow = StateGraph(IngestionState)
    
    workflow.add_node("docparse", node_docparse)
    workflow.add_node("canonical_load", node_canonical_load)
    
    workflow.set_entry_point("docparse")
    
    workflow.add_edge("docparse", "canonical_load")
    workflow.add_edge("canonical_load", END)
    
    return workflow.compile(checkpointer=checkpointer)

def setup_checkpointer():
    pool = ConnectionPool(conninfo=DB_DSN)
    checkpointer = PostgresSaver(pool)
    checkpointer.setup() # Ensures tables exist
    return checkpointer
