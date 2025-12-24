import json
import logging
import os
import sys
from typing import TypedDict, Annotated, List, Dict, Any, Optional
from uuid import UUID

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver 

from tpa_api.ingest_worker import (
    _call_docparse_bundle,
    _load_parse_bundle,
    _persist_pages,
    _persist_layout_blocks,
    _persist_visual_assets,
    _persist_bundle_evidence_refs,
    _persist_chunks_from_blocks,
    _insert_parse_bundle_record,
    _llm_extract_policy_structure,
    _persist_policy_structure,
    _segment_visual_assets,
    _vectorize_segmentation_masks,
    _auto_georef_visual_assets,
    _embed_units,
    _start_run_step,
    _finish_run_step,
    init_db_pool,
    _db_fetch_one,
    _db_fetch_all,
    _db_execute
)

from tpa_api.ingestion.prompts_rich import (
    _vlm_enrich_visual_asset, 
    _llm_enrich_policy_structure,
    _llm_imagination_synthesis
)
from tpa_api.blob_store import read_blob_bytes

logger = logging.getLogger(__name__)

def log(msg):
    print(msg, flush=True)

def _clean_db_rows(rows: List[Dict]) -> List[Dict]:
    out = []
    for r in rows:
        nr = {}
        for k, v in r.items():
            if isinstance(v, UUID):
                nr[k] = str(v)
            else:
                nr[k] = v
        out.append(nr)
    return out

class IngestionState(TypedDict):
    run_id: str
    ingest_job_id: str
    ingest_batch_id: str
    authority_id: str
    plan_cycle_id: Optional[str]
    document_id: str
    filename: str
    file_bytes: bytes
    doc_metadata: dict
    bundle_path: Optional[str]
    visual_queue: List[Dict] 
    text_queue: List[Dict]   
    rich_policies: List[Dict]
    rich_visuals: List[Dict]
    error: Optional[str]

def node_docparse(state: IngestionState) -> IngestionState:
    try:
        log(f"--- Node: DocParse ---")
        _start_run_step(run_id=state['run_id'], ingest_batch_id=state['ingest_batch_id'], step_name="docling_parse", inputs={"filename": state['filename']})
        existing = _db_fetch_one("SELECT blob_path FROM parse_bundles WHERE document_id = %s::uuid", (state['document_id'],))
        if existing:
            bundle_path = existing['blob_path']
            _finish_run_step(run_id=state['run_id'], step_name="docling_parse", status="completed", outputs={"skipped": True, "parse_bundle_path": bundle_path})
            return {**state, "bundle_path": bundle_path}
        result = _call_docparse_bundle(file_bytes=state['file_bytes'], filename=state['filename'], metadata=state['doc_metadata'], ingest_batch_id=state['ingest_batch_id'], run_id=state['run_id'])
        path = result.get('parse_bundle_path')
        _finish_run_step(run_id=state['run_id'], step_name="docling_parse", status="completed", outputs={"parse_bundle_path": path})
        return {**state, "bundle_path": path}
    except Exception as e:
        log(f"!!! DocParse Failed: {e}")
        _finish_run_step(run_id=state['run_id'], step_name="docling_parse", status="failed", outputs={}, error_text=str(e))
        return {**state, "error": str(e)}

def node_shard_assets(state: IngestionState) -> IngestionState:
    if state.get('error'): return state
    try:
        log(f"--- Node: Shard Assets ---")
        _start_run_step(run_id=state['run_id'], ingest_batch_id=state['ingest_batch_id'], step_name="canonical_load", inputs={})
        bundle = _load_parse_bundle(state['bundle_path'])
        try:
            _insert_parse_bundle_record(
                ingest_job_id=state['ingest_job_id'], ingest_batch_id=state['ingest_batch_id'], 
                run_id=state['run_id'], document_id=state['document_id'], 
                schema_version=bundle.get("schema_version") or "2.0", blob_path=state['bundle_path'], metadata={}
            )
            pages = bundle.get("pages") or []
            _persist_pages(document_id=state['document_id'], ingest_batch_id=state['ingest_batch_id'], run_id=state['run_id'], source_artifact_id=None, pages=pages)
            ref_map = _persist_bundle_evidence_refs(run_id=state['run_id'], evidence_refs=bundle.get("evidence_refs") or [])
            blocks = bundle.get("layout_blocks") or []
            block_rows = _persist_layout_blocks(document_id=state['document_id'], ingest_batch_id=state['ingest_batch_id'], run_id=state['run_id'], source_artifact_id=None, pages=pages, blocks=blocks, evidence_ref_map=ref_map)
            _persist_chunks_from_blocks(document_id=state['document_id'], ingest_batch_id=state['ingest_batch_id'], run_id=state['run_id'], source_artifact_id=None, block_rows=block_rows)
            _persist_visual_assets(document_id=state['document_id'], ingest_batch_id=state['ingest_batch_id'], run_id=state['run_id'], source_artifact_id=None, visual_assets=bundle.get("visual_assets") or [], evidence_ref_map=ref_map)
        except Exception as e:
            if "already exists" in str(e): log("   (Data already persisted)")
            else: log(f"   (Partial error: {e})")

        visuals = _clean_db_rows(_db_fetch_all("SELECT id, blob_path, metadata FROM visual_assets WHERE document_id = %s::uuid", (state['document_id'],)))
        blocks = _clean_db_rows(_db_fetch_all("SELECT id as block_id, text, page_number FROM layout_blocks WHERE document_id = %s::uuid", (state['document_id'],)))
        
        _finish_run_step(run_id=state['run_id'], step_name="canonical_load", status="completed", outputs={"visual_count": len(visuals)})
        return {**state, "visual_queue": visuals, "text_queue": blocks}
    except Exception as e:
        _finish_run_step(run_id=state['run_id'], step_name="canonical_load", status="failed", outputs={}, error_text=str(e))
        return {**state, "error": str(e)}

def node_vlm_batch(state: IngestionState) -> IngestionState:
    if state.get('error'): return state
    visuals = state.get('visual_queue', [])
    log(f"--- Node: VLM Batch (Count: {len(visuals)}) ---")
    
    # IDEMPOTENCY CHECK
    to_enrich = [v for v in visuals if "rich_enrichment" not in (v.get('metadata') or {})]
    
    if not to_enrich:
        log("   -> All assets already enriched. Skipping VLM Pass.")
        # Load existing rich visuals into state for downstream imagination
        rich_visuals = []
        for v in visuals:
            rich_visuals.append({**v, "rich_enrichment": v['metadata'].get('rich_enrichment')})
        return {**state, "rich_visuals": rich_visuals}

    log(f"   -> Processing {len(to_enrich)} / {len(visuals)} assets.")
    rich_results = []
    try:
        _start_run_step(run_id=state['run_id'], ingest_batch_id=state['ingest_batch_id'], step_name="visual_pipeline_batch", inputs={})
        for idx, asset in enumerate(to_enrich):
            img_bytes, _, _ = read_blob_bytes(asset['blob_path'])
            if img_bytes:
                log(f"   [{idx+1}/{len(to_enrich)}] Enriching Asset: {asset['id']}")
                rich_meta = _vlm_enrich_visual_asset(asset, img_bytes)
                _db_execute("UPDATE visual_assets SET metadata = metadata || %s::jsonb WHERE id = %s::uuid", (json.dumps({"rich_enrichment": rich_meta}), asset['id']))
                rich_results.append({**asset, "rich_enrichment": rich_meta})
        
        # SAM2/Georef (can also be made idempotent later)
        _segment_visual_assets(ingest_batch_id=state['ingest_batch_id'], run_id=state['run_id'], authority_id=state['authority_id'], plan_cycle_id=state['plan_cycle_id'], document_id=state['document_id'], visual_assets=to_enrich)
        
        _finish_run_step(run_id=state['run_id'], step_name="visual_pipeline_batch", status="completed", outputs={})
        
        # Merge old and new for downstream
        all_rich = []
        for v in visuals:
            if "rich_enrichment" in (v.get('metadata') or {}):
                all_rich.append({**v, "rich_enrichment": v['metadata']['rich_enrichment']})
            else:
                # Find the one we just processed
                match = next((r for r in rich_results if r['id'] == v['id']), None)
                if match: all_rich.append(match)

        return {**state, "rich_visuals": all_rich}
    except Exception as e:
        log(f"!!! VLM Batch Failed: {e}")
        _finish_run_step(run_id=state['run_id'], step_name="visual_pipeline_batch", status="failed", outputs={}, error_text=str(e))
        return {**state, "error": str(e)}

def node_llm_batch(state: IngestionState) -> IngestionState:
    if state.get('error') or not state['text_queue']: 
        return {**state, "structure_complete": True}
    try:
        log(f"--- Node: LLM Batch ---")
        
        doc = _db_fetch_one("SELECT metadata FROM documents WHERE id = %s::uuid", (state['document_id'],))
        existing_policies = (doc.get('metadata') or {}).get('rich_policy_structure')
        if existing_policies and len(existing_policies) > 0:
            log(f"   -> Found {len(existing_policies)} existing policies. Skipping LLM Pass.")
            return {**state, "rich_policies": existing_policies}

        _start_run_step(run_id=state['run_id'], ingest_batch_id=state['ingest_batch_id'], step_name="structural_pipeline_batch", inputs={})
        
        # BATCHING SLICER
        blocks = state['text_queue']
        batch_size = 50 
        all_rich_policies = []
        
        for i in range(0, len(blocks), batch_size):
            batch = blocks[i : i + batch_size]
            log(f"   -> Processing Block Batch {i//batch_size + 1} ({len(batch)} blocks)...")
            
            rich_policies = _llm_enrich_policy_structure(
                document_title=state['doc_metadata'].get('title', 'Unknown'),
                blocks=batch,
                run_id=state['run_id']
            )
            all_rich_policies.extend(rich_policies)
            log(f"      (Found {len(rich_policies)} policies)")

        log(f"   -> Total Extracted: {len(all_rich_policies)} rich policies.")
        _db_execute("UPDATE documents SET metadata = metadata || %s::jsonb WHERE id = %s::uuid", (json.dumps({"rich_policy_structure": all_rich_policies}), state['document_id']))
        _finish_run_step(run_id=state['run_id'], step_name="structural_pipeline_batch", status="completed", outputs={"count": len(all_rich_policies)})
        return {**state, "rich_policies": all_rich_policies}
    except Exception as e:
        log(f"!!! LLM Batch Failed: {e}")
        _finish_run_step(run_id=state['run_id'], step_name="structural_pipeline_batch", status="failed", outputs={}, error_text=str(e))
        return {**state, "error": str(e)}

def node_imagination(state: IngestionState) -> IngestionState:
    if state.get('error'): return state
    try:
        log(f"--- Node: Imagination Synthesis ---")
        
        # IDEMPOTENCY CHECK - Only skip if NOT EMPTY
        doc = _db_fetch_one("SELECT metadata FROM documents WHERE id = %s::uuid", (state['document_id'],))
        existing_imagination = (doc.get('metadata') or {}).get('imagination_synthesis')
        if existing_imagination and len(existing_imagination.get('qa_seeds', [])) > 0:
            log("   -> Imagination already synthesized. Skipping.")
            return state

        _start_run_step(run_id=state['run_id'], ingest_batch_id=state['ingest_batch_id'], step_name="imagination_synthesis", inputs={})
        
        # We need to load policies and visuals into state if they were skipped
        rich_policies = state.get('rich_policies') or (doc.get('metadata') or {}).get('rich_policy_structure') or []
        
        # visuals are in visual_queue but we need the 'rich_enrichment' part
        visuals = state.get('rich_visuals')
        if not visuals:
             log("   (Loading rich visuals from DB for synthesis)")
             visual_rows = _db_fetch_all("SELECT id, metadata FROM visual_assets WHERE document_id = %s::uuid", (state['document_id'],))
             visuals = []
             for v in visual_rows:
                 if v['metadata'] and 'rich_enrichment' in v['metadata']:
                     visuals.append({"id": str(v['id']), "asset_category": v['metadata']['rich_enrichment'].get('asset_category'), "interpretation_notes": v['metadata']['rich_enrichment'].get('interpretation_notes')})

        synthesis = _llm_imagination_synthesis(state['document_id'], rich_policies, visuals, state['run_id'])
        
        log(f"   -> Linked {len(synthesis.get('cross_modal_links', []))} policies to visuals.")
        log(f"   -> Identified {len(synthesis.get('potential_conflicts', []))} potential conflicts.")
        
        _db_execute("UPDATE documents SET metadata = metadata || %s::jsonb WHERE id = %s::uuid", (json.dumps({"imagination_synthesis": synthesis}), state['document_id']))
        _finish_run_step(run_id=state['run_id'], step_name="imagination_synthesis", status="completed", outputs={})
        return state
    except Exception as e:
        log(f"!!! Imagination Failed: {e}")
        _finish_run_step(run_id=state['run_id'], step_name="imagination_synthesis", status="failed", outputs={}, error_text=str(e))
        return {**state, "error": str(e)}

def node_finalize(state: IngestionState) -> IngestionState:
    """Updates the Ingest Job status to completed."""
    if state.get('error'):
        _db_execute("UPDATE ingest_jobs SET status = 'failed', error_text = %s, completed_at = NOW() WHERE id = %s::uuid", (state['error'], state['ingest_job_id']))
        log("🏁 Graph Finished with Errors")
    else:
        _db_execute("UPDATE ingest_jobs SET status = 'completed', completed_at = NOW() WHERE id = %s::uuid", (state['ingest_job_id'],))
        log("🎉 Graph Finished Successfully")
    return state

def build_ingestion_graph(checkpointer=None):
    workflow = StateGraph(IngestionState)
    workflow.add_node("docparse", node_docparse)
    workflow.add_node("shard", node_shard_assets)
    workflow.add_node("vlm_batch", node_vlm_batch)
    workflow.add_node("llm_batch", node_llm_batch)
    workflow.add_node("imagination", node_imagination)
    workflow.add_node("finalize", node_finalize)
    
    workflow.set_entry_point("docparse")
    workflow.add_edge("docparse", "shard")
    workflow.add_edge("shard", "vlm_batch")
    workflow.add_edge("vlm_batch", "llm_batch")
    workflow.add_edge("llm_batch", "imagination")
    workflow.add_edge("imagination", "finalize")
    workflow.add_edge("finalize", END)
    return workflow.compile(checkpointer=checkpointer)