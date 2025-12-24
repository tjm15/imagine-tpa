import json
import logging
import os
from typing import TypedDict, List, Dict, Any, Optional
from uuid import UUID

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from tpa_api.db import (
    init_db_pool,
    _db_fetch_one,
    _db_fetch_all,
    _db_execute,
)
from tpa_api.blob_store import (
    minio_client_or_none,
    read_blob_bytes,
)

from tpa_api.ingestion.ops import (
    _call_docparse_bundle,
    _load_parse_bundle,
    _insert_parse_bundle_record,
    _persist_tool_runs,
    _persist_pages,
    _persist_layout_blocks,
    _persist_document_tables,
    _persist_vector_paths,
    _persist_chunks_from_blocks,
    _persist_visual_assets,
    _persist_bundle_evidence_refs,
    _persist_visual_features,
    _persist_visual_semantic_features,
    _persist_visual_rich_enrichment,
    _extract_visual_asset_facts,
    _extract_visual_text_snippets,
    _segment_visual_assets,
    _vectorize_segmentation_masks,
    _extract_visual_region_assertions,
    _auto_georef_visual_assets,
    _extract_visual_agent_findings,
    _extract_document_identity_status,
    _llm_extract_policy_structure,
    _merge_policy_headings,
    _persist_policy_structure,
    _llm_extract_policy_logic_assets,
    _merge_policy_logic_assets,
    _persist_policy_logic_assets,
    _llm_extract_edges,
    _persist_policy_edges,
    _propose_visual_policy_links,
    _persist_visual_policy_links_from_proposals,
    _embed_units,
    _embed_visual_assets,
    _embed_visual_assertions,
    _persist_kg_nodes,
    _ensure_artifact,
    _ensure_document_row,
    _store_raw_blob,
    _update_run_step_progress,
)

from tpa_api.ingestion.prompts_rich import _llm_imagination_synthesis, _vlm_enrich_visual_asset
from tpa_api.observability.phoenix import trace_span

logger = logging.getLogger(__name__)


def log(msg: str) -> None:
    print(msg, flush=True)


def _clean_db_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        cleaned: Dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, UUID):
                cleaned[key] = str(value)
            else:
                cleaned[key] = value
        out.append(cleaned)
    return out


def _bump(state: "IngestionState", key: str, delta: int) -> None:
    counts = state.setdefault("counts", {})
    counts[key] = counts.get(key, 0) + delta


def _mark_step(state: "IngestionState", step_name: str) -> None:
    steps = state.setdefault("steps_completed", [])
    steps.append(step_name)


def _progress(state: "IngestionState", step_name: str, outputs: Dict[str, Any], status: str = "running") -> None:
    run_id = state.get("run_id")
    if not run_id:
        return
    _update_run_step_progress(run_id=run_id, step_name=step_name, outputs=outputs, status=status)


class IngestionState(TypedDict, total=False):
    run_id: str
    ingest_job_id: str
    ingest_batch_id: str
    authority_id: str
    plan_cycle_id: Optional[str]
    filename: str
    file_bytes: bytes
    doc_metadata: Dict[str, Any]
    source_url: Optional[str]
    content_type: Optional[str]

    document_id: str
    raw_blob_path: str
    raw_sha256: str
    raw_artifact_id: str

    bundle_path: str
    bundle_semantic: Dict[str, Any]
    evidence_ref_map: Dict[str, str]
    pages: List[Dict[str, Any]]
    page_texts: Dict[int, str]
    block_rows: List[Dict[str, Any]]
    chunk_rows: List[Dict[str, Any]]
    visual_rows: List[Dict[str, Any]]

    policy_sections: List[Dict[str, Any]]
    policy_clauses: List[Dict[str, Any]]
    definitions: List[Dict[str, Any]]
    targets: List[Dict[str, Any]]
    monitoring: List[Dict[str, Any]]
    links_by_asset: Dict[str, List[Dict[str, Any]]]

    counts: Dict[str, int]
    steps_completed: List[str]
    errors: List[str]
    error: Optional[str]


def node_anchor_raw(state: IngestionState) -> IngestionState:
    if state.get("error"):
        return state
    try:
        with trace_span(
            "ingest.node",
            {
                "tpa.step": "anchor_raw",
                "tpa.run_id": state.get("run_id"),
                "tpa.authority_id": state.get("authority_id"),
            },
        ) as span:
            init_db_pool()
            log("--- Node: Anchor Raw ---")
            client = minio_client_or_none()
            bucket = os.environ.get("TPA_S3_BUCKET")
            filename = state["filename"]
            data = state["file_bytes"]
            authority_id = state["authority_id"]

            raw_blob_path, raw_sha256 = _store_raw_blob(
                client=client,
                bucket=bucket,
                authority_id=authority_id,
                filename=filename,
                data=data,
            )
            raw_artifact_id = _ensure_artifact(artifact_type="raw_pdf", path=raw_blob_path)
            doc_metadata = state.get("doc_metadata") or {}
            content_type = state.get("content_type")
            source_url = state.get("source_url")
            raw_source_uri = source_url or filename
            document_id = _ensure_document_row(
                authority_id=authority_id,
                plan_cycle_id=state.get("plan_cycle_id"),
                ingest_batch_id=state.get("ingest_batch_id"),
                run_id=state.get("run_id"),
                blob_path=raw_blob_path,
                metadata=doc_metadata,
                raw_blob_path=raw_blob_path,
                raw_sha256=raw_sha256,
                raw_bytes=len(data),
                raw_content_type=content_type,
                raw_source_uri=raw_source_uri,
                raw_artifact_id=raw_artifact_id,
            )
            if span is not None:
                span.set_attribute("tpa.document_id", document_id)

            _bump(state, "documents_seen", 1)
            _mark_step(state, "anchor_raw")
            _progress(
                state,
                "anchor_raw",
                {
                    "documents": state["counts"].get("documents_seen", 0),
                    "last_document_id": document_id,
                    "last_filename": filename,
                },
            )

            return {
                **state,
                "document_id": document_id,
                "raw_blob_path": raw_blob_path,
                "raw_sha256": raw_sha256,
                "raw_artifact_id": raw_artifact_id,
            }
    except Exception as exc:  # noqa: BLE001
        log(f"!!! Anchor Raw Failed: {exc}")
        _progress(state, "anchor_raw", {"error": str(exc)}, status="error")
        return {**state, "error": str(exc)}


def node_docparse(state: IngestionState) -> IngestionState:
    if state.get("error"):
        return state
    try:
        with trace_span(
            "ingest.node",
            {
                "tpa.step": "docling_parse",
                "tpa.run_id": state.get("run_id"),
                "tpa.document_id": state.get("document_id"),
            },
        ) as span:
            log("--- Node: DocParse ---")
            document_id = state["document_id"]
            existing = _db_fetch_one("SELECT blob_path FROM parse_bundles WHERE document_id = %s::uuid", (document_id,))
            if existing:
                bundle_path = existing.get("blob_path")
                if isinstance(bundle_path, str):
                    _mark_step(state, "docling_parse")
                    _progress(
                        state,
                        "docling_parse",
                        {"documents": state["counts"].get("documents_seen", 0), "parse_bundle_path": bundle_path},
                    )
                    return {**state, "bundle_path": bundle_path}

            result = _call_docparse_bundle(
                file_bytes=state["file_bytes"],
                filename=state["filename"],
                metadata={
                    "authority_id": state["authority_id"],
                    "plan_cycle_id": state.get("plan_cycle_id"),
                    "document_id": document_id,
                    "job_id": state.get("ingest_job_id"),
                    "source_url": state.get("source_url"),
                },
                ingest_batch_id=state.get("ingest_batch_id"),
                run_id=state.get("run_id"),
            )
            bundle_path = result.get("parse_bundle_path")
            if not isinstance(bundle_path, str):
                raise RuntimeError("parse_bundle_missing")
            if span is not None:
                span.set_attribute("tpa.parse_bundle_path", bundle_path)

            _mark_step(state, "docling_parse")
            _progress(
                state,
                "docling_parse",
                {"documents": state["counts"].get("documents_seen", 0), "parse_bundle_path": bundle_path},
            )
            return {**state, "bundle_path": bundle_path}
    except Exception as exc:  # noqa: BLE001
        log(f"!!! DocParse Failed: {exc}")
        _progress(state, "docling_parse", {"error": str(exc)}, status="error")
        return {**state, "error": str(exc)}


def node_canonical_load(state: IngestionState) -> IngestionState:
    if state.get("error"):
        return state
    try:
        log("--- Node: Canonical Load ---")
        bundle = _load_parse_bundle(state["bundle_path"])
        semantic = bundle.get("semantic") if isinstance(bundle.get("semantic"), dict) else {}

        _insert_parse_bundle_record(
            ingest_job_id=state["ingest_job_id"],
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            document_id=state["document_id"],
            schema_version=bundle.get("schema_version") or "2.0",
            blob_path=state["bundle_path"],
            metadata={
                "tables_unimplemented": bool(bundle.get("tables_unimplemented")),
                "parse_flags": bundle.get("parse_flags") if isinstance(bundle.get("parse_flags"), list) else [],
                "tool_run_count": len(bundle.get("tool_runs") or []),
            },
        )

        tool_runs = bundle.get("tool_runs") if isinstance(bundle.get("tool_runs"), list) else []
        _persist_tool_runs(ingest_batch_id=state["ingest_batch_id"], run_id=state.get("run_id"), tool_runs=tool_runs)

        pages = bundle.get("pages") if isinstance(bundle.get("pages"), list) else []
        _persist_pages(
            document_id=state["document_id"],
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            source_artifact_id=state.get("raw_artifact_id"),
            pages=pages,
        )
        _bump(state, "pages", len(pages))

        evidence_refs = bundle.get("evidence_refs") if isinstance(bundle.get("evidence_refs"), list) else []
        evidence_ref_map = _persist_bundle_evidence_refs(run_id=state.get("run_id"), evidence_refs=evidence_refs)

        blocks = bundle.get("layout_blocks") if isinstance(bundle.get("layout_blocks"), list) else []
        block_rows = _persist_layout_blocks(
            document_id=state["document_id"],
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            source_artifact_id=state.get("raw_artifact_id"),
            pages=pages,
            blocks=blocks,
            evidence_ref_map=evidence_ref_map,
        )
        _bump(state, "layout_blocks", len(block_rows))

        tables = bundle.get("tables") if isinstance(bundle.get("tables"), list) else []
        _persist_document_tables(
            document_id=state["document_id"],
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            source_artifact_id=state.get("raw_artifact_id"),
            tables=tables,
        )
        _bump(state, "tables", len(tables))

        vector_paths = bundle.get("vector_paths") if isinstance(bundle.get("vector_paths"), list) else []
        _persist_vector_paths(
            document_id=state["document_id"],
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            source_artifact_id=state.get("raw_artifact_id"),
            vector_paths=vector_paths,
        )
        _bump(state, "vector_paths", len(vector_paths))

        chunk_rows = _persist_chunks_from_blocks(
            document_id=state["document_id"],
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            source_artifact_id=state.get("raw_artifact_id"),
            block_rows=block_rows,
        )
        _bump(state, "chunks", len(chunk_rows))

        visual_assets = bundle.get("visual_assets") if isinstance(bundle.get("visual_assets"), list) else []
        visual_rows = _persist_visual_assets(
            document_id=state["document_id"],
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            source_artifact_id=state.get("raw_artifact_id"),
            visual_assets=visual_assets,
            evidence_ref_map=evidence_ref_map,
        )
        _bump(state, "visual_assets", len(visual_rows))
        _persist_visual_features(visual_assets=visual_rows, run_id=state.get("run_id"))
        _persist_visual_semantic_features(visual_assets=visual_rows, semantic=semantic, run_id=state.get("run_id"))

        page_texts = {int(p.get("page_number") or 0): str(p.get("text") or "") for p in pages}

        _mark_step(state, "canonical_load")
        _progress(
            state,
            "canonical_load",
            {
                "documents": state["counts"].get("documents_seen", 0),
                "pages": state["counts"].get("pages", 0),
                "layout_blocks": state["counts"].get("layout_blocks", 0),
                "tables": state["counts"].get("tables", 0),
                "vector_paths": state["counts"].get("vector_paths", 0),
                "chunks": state["counts"].get("chunks", 0),
                "visual_assets": state["counts"].get("visual_assets", 0),
                "last_document_id": state["document_id"],
            },
        )

        return {
            **state,
            "bundle_semantic": semantic,
            "evidence_ref_map": evidence_ref_map,
            "pages": pages,
            "page_texts": page_texts,
            "block_rows": _clean_db_rows(block_rows),
            "chunk_rows": _clean_db_rows(chunk_rows),
            "visual_rows": _clean_db_rows(visual_rows),
        }
    except Exception as exc:  # noqa: BLE001
        log(f"!!! Canonical Load Failed: {exc}")
        _progress(state, "canonical_load", {"error": str(exc)}, status="error")
        return {**state, "error": str(exc)}


def node_visual_pipeline(state: IngestionState) -> IngestionState:
    if state.get("error"):
        return state
    visual_rows = state.get("visual_rows") or []
    if not visual_rows:
        return state

    try:
        log(f"--- Node: Visual Pipeline ({len(visual_rows)} assets) ---")

        # Rich VLM enrichment (planner-focused summary)
        for asset in visual_rows:
            visual_asset_id = asset.get("visual_asset_id")
            if not visual_asset_id:
                continue
            metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            if metadata.get("rich_enrichment"):
                continue
            blob_path = asset.get("blob_path")
            if not isinstance(blob_path, str):
                continue
            image_bytes, _, err = read_blob_bytes(blob_path)
            if err or not image_bytes:
                continue
            rich_meta, tool_run_id, _ = _vlm_enrich_visual_asset(asset, image_bytes, run_id=state.get("run_id"))
            _persist_visual_rich_enrichment(
                visual_asset_id=visual_asset_id,
                run_id=state.get("run_id"),
                tool_run_id=tool_run_id,
                enrichment=rich_meta,
            )
            _db_execute(
                "UPDATE visual_assets SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb WHERE id = %s::uuid",
                (json.dumps({"rich_enrichment": rich_meta}, ensure_ascii=False), visual_asset_id),
            )

        visual_facts_count = _extract_visual_asset_facts(
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            visual_assets=visual_rows,
        )
        _bump(state, "visual_semantic_assets", visual_facts_count)
        _mark_step(state, "visual_semantics_asset")

        text_snippet_count = _extract_visual_text_snippets(
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            visual_assets=visual_rows,
        )
        _bump(state, "visual_text_snippets", text_snippet_count)
        _progress(
            state,
            "visual_semantics_asset",
            {
                "visual_assets": state["counts"].get("visual_assets", 0),
                "visual_semantic_assets": state["counts"].get("visual_semantic_assets", 0),
                "visual_text_snippets": state["counts"].get("visual_text_snippets", 0),
            },
        )

        mask_count, region_count = _segment_visual_assets(
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            authority_id=state["authority_id"],
            plan_cycle_id=state.get("plan_cycle_id"),
            document_id=state["document_id"],
            visual_assets=visual_rows,
        )
        _bump(state, "segmentation_masks", mask_count)
        _bump(state, "visual_asset_regions", region_count)
        _mark_step(state, "visual_segmentation")
        _progress(
            state,
            "visual_segmentation",
            {
                "segmentation_masks": state["counts"].get("segmentation_masks", 0),
                "visual_asset_regions": state["counts"].get("visual_asset_regions", 0),
            },
        )

        vector_count = _vectorize_segmentation_masks(
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            document_id=state["document_id"],
            visual_assets=visual_rows,
        )
        _bump(state, "vector_paths", vector_count)
        _mark_step(state, "visual_vectorization")
        _progress(
            state,
            "visual_vectorization",
            {"vector_paths": state["counts"].get("vector_paths", 0)},
        )

        assertion_count = _extract_visual_region_assertions(
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            visual_assets=visual_rows,
        )
        _bump(state, "visual_semantic_assertions", assertion_count)
        _mark_step(state, "visual_semantics_regions")
        _progress(
            state,
            "visual_semantics_regions",
            {"visual_semantic_assertions": state["counts"].get("visual_semantic_assertions", 0)},
        )

        target_epsg = int(os.environ.get("TPA_GEOREF_TARGET_EPSG", "27700"))
        georef_attempts, georef_success, transform_count, projection_count = _auto_georef_visual_assets(
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            visual_assets=visual_rows,
            target_epsg=target_epsg,
        )
        _bump(state, "georef_attempts", georef_attempts)
        _bump(state, "georef_success", georef_success)
        _bump(state, "transforms", transform_count)
        _bump(state, "projection_artifacts", projection_count)
        _mark_step(state, "visual_georef")
        _progress(
            state,
            "visual_georef",
            {
                "georef_attempts": state["counts"].get("georef_attempts", 0),
                "georef_success": state["counts"].get("georef_success", 0),
                "transforms": state["counts"].get("transforms", 0),
                "projection_artifacts": state["counts"].get("projection_artifacts", 0),
            },
        )

        return state
    except Exception as exc:  # noqa: BLE001
        log(f"!!! Visual Pipeline Failed: {exc}")
        _progress(state, "visual_semantics_asset", {"error": str(exc)}, status="error")
        return {**state, "error": str(exc)}


def node_document_identity(state: IngestionState) -> IngestionState:
    if state.get("error"):
        return state
    try:
        log("--- Node: Document Identity ---")
        block_rows = state.get("block_rows") or []
        evidence_ref_map = state.get("evidence_ref_map") or {}
        identity_bundle, _, identity_errors = _extract_document_identity_status(
            ingest_batch_id=state.get("ingest_batch_id"),
            run_id=state.get("run_id"),
            document_id=state["document_id"],
            title=state.get("doc_metadata", {}).get("title") or state["filename"],
            filename=state["filename"],
            content_type=state.get("content_type"),
            block_rows=block_rows,
            evidence_ref_map=evidence_ref_map,
        )
        if identity_bundle:
            _bump(state, "document_identity_status", 1)
            _mark_step(state, "document_identity_status")
        if identity_errors:
            errors = state.setdefault("errors", [])
            errors.extend([f"document_identity:{err}" for err in identity_errors])
        _progress(state, "document_identity_status", {"documents": state["counts"].get("document_identity_status", 0)})
        return state
    except Exception as exc:  # noqa: BLE001
        log(f"!!! Document Identity Failed: {exc}")
        _progress(state, "document_identity_status", {"error": str(exc)}, status="error")
        return {**state, "error": str(exc)}


def node_structural_llm(state: IngestionState) -> IngestionState:
    if state.get("error"):
        return state
    try:
        log("--- Node: Structural LLM ---")
        semantic = state.get("bundle_semantic") or {}
        policy_headings = semantic.get("policy_headings") if isinstance(semantic.get("policy_headings"), list) else []
        block_rows = state.get("block_rows") or []

        sections, _, struct_errors = _llm_extract_policy_structure(
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            document_id=state["document_id"],
            document_title=state.get("doc_metadata", {}).get("title") or state["filename"],
            blocks=block_rows,
            policy_headings=policy_headings,
        )
        if policy_headings and not sections:
            fallback_sections, _, fallback_errors = _llm_extract_policy_structure(
                ingest_batch_id=state["ingest_batch_id"],
                run_id=state.get("run_id"),
                document_id=state["document_id"],
                document_title=state.get("doc_metadata", {}).get("title") or state["filename"],
                blocks=block_rows,
            )
            sections = fallback_sections
            struct_errors.extend([f"policy_structure_fallback:{err}" for err in fallback_errors])
        if not policy_headings:
            sections = _merge_policy_headings(sections=sections, policy_headings=policy_headings, block_rows=block_rows)
        if struct_errors:
            errors = state.setdefault("errors", [])
            errors.extend([f"policy_structure:{err}" for err in struct_errors])

        policy_sections, policy_clauses, definitions, targets, monitoring = _persist_policy_structure(
            document_id=state["document_id"],
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            source_artifact_id=state.get("raw_artifact_id"),
            sections=sections,
            block_rows=block_rows,
        )
        _bump(state, "policy_sections", len(policy_sections))
        _bump(state, "policy_clauses", len(policy_clauses))
        _bump(state, "definitions", len(definitions))
        _bump(state, "targets", len(targets))
        _bump(state, "monitoring", len(monitoring))

        llm_matrices, llm_scopes, logic_errors = _llm_extract_policy_logic_assets(
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            document_id=state["document_id"],
            document_title=state.get("doc_metadata", {}).get("title") or state["filename"],
            policy_sections=policy_sections,
            block_rows=block_rows,
        )
        if logic_errors:
            errors = state.setdefault("errors", [])
            errors.extend([f"policy_logic_assets:{err}" for err in logic_errors])

        merged_matrices, merged_scopes = _merge_policy_logic_assets(
            docparse_matrices=semantic.get("standard_matrices") if isinstance(semantic.get("standard_matrices"), list) else [],
            llm_matrices=llm_matrices,
            docparse_scopes=semantic.get("scope_candidates") if isinstance(semantic.get("scope_candidates"), list) else [],
            llm_scopes=llm_scopes,
            sections=sections,
            policy_sections=policy_sections,
            block_rows=block_rows,
        )

        matrix_count, scope_count = _persist_policy_logic_assets(
            document_id=state["document_id"],
            run_id=state.get("run_id"),
            sections=sections,
            policy_sections=policy_sections,
            standard_matrices=merged_matrices,
            scope_candidates=merged_scopes,
            evidence_ref_map=state.get("evidence_ref_map") or {},
            block_rows=block_rows,
        )
        _bump(state, "policy_matrices", matrix_count)
        _bump(state, "policy_scopes", scope_count)

        policy_codes = [s.get("policy_code") for s in policy_sections if s.get("policy_code")]
        citations, mentions, conditions, edge_tool_run_ids, edge_errors = _llm_extract_edges(
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            policy_clauses=policy_clauses,
            policy_codes=policy_codes,
        )
        if edge_errors:
            errors = state.setdefault("errors", [])
            errors.extend([f"policy_edges:{err}" for err in edge_errors])
        _persist_policy_edges(
            policy_sections=policy_sections,
            policy_clauses=policy_clauses,
            definitions=definitions,
            targets=targets,
            monitoring=monitoring,
            citations=citations,
            mentions=mentions,
            conditions=conditions,
            block_rows=block_rows,
            tool_run_ids=edge_tool_run_ids,
            run_id=state.get("run_id"),
        )

        _persist_kg_nodes(
            document_id=state["document_id"],
            chunks=state.get("chunk_rows") or [],
            visual_assets=state.get("visual_rows") or [],
            policy_sections=policy_sections,
            policy_clauses=policy_clauses,
            definitions=definitions,
            targets=targets,
            monitoring=monitoring,
        )

        agent_count = _extract_visual_agent_findings(
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            visual_assets=state.get("visual_rows") or [],
        )
        _bump(state, "visual_semantic_agents", agent_count)

        _mark_step(state, "structural_llm")
        _mark_step(state, "edges_llm")
        _progress(
            state,
            "structural_llm",
            {
                "policy_sections": state["counts"].get("policy_sections", 0),
                "policy_clauses": state["counts"].get("policy_clauses", 0),
                "definitions": state["counts"].get("definitions", 0),
                "targets": state["counts"].get("targets", 0),
                "monitoring": state["counts"].get("monitoring", 0),
                "policy_matrices": state["counts"].get("policy_matrices", 0),
                "policy_scopes": state["counts"].get("policy_scopes", 0),
            },
        )
        _progress(state, "edges_llm", {"documents": state["counts"].get("documents_seen", 0)})

        return {
            **state,
            "policy_sections": _clean_db_rows(policy_sections),
            "policy_clauses": _clean_db_rows(policy_clauses),
            "definitions": _clean_db_rows(definitions),
            "targets": _clean_db_rows(targets),
            "monitoring": _clean_db_rows(monitoring),
        }
    except Exception as exc:  # noqa: BLE001
        log(f"!!! Structural LLM Failed: {exc}")
        _progress(state, "structural_llm", {"error": str(exc)}, status="error")
        return {**state, "error": str(exc)}


def node_visual_linking(state: IngestionState) -> IngestionState:
    if state.get("error"):
        return state
    visual_rows = state.get("visual_rows") or []
    policy_sections = state.get("policy_sections") or []
    if not visual_rows or not policy_sections:
        return state
    try:
        log("--- Node: Visual Linking ---")
        link_proposals, _ = _propose_visual_policy_links(
            ingest_batch_id=state["ingest_batch_id"],
            run_id=state.get("run_id"),
            visual_assets=visual_rows,
            policy_sections=policy_sections,
            page_texts=state.get("page_texts") or {},
        )
        links_by_asset, link_count = _persist_visual_policy_links_from_proposals(
            run_id=state.get("run_id"),
            proposals_by_asset=link_proposals,
            visual_assets=visual_rows,
            policy_sections=policy_sections,
        )
        _bump(state, "visual_asset_links", link_count)
        _mark_step(state, "visual_linking")
        _progress(
            state,
            "visual_linking",
            {
                "visual_assets": state["counts"].get("visual_assets", 0),
                "visual_asset_links": state["counts"].get("visual_asset_links", 0),
            },
        )
        return {**state, "links_by_asset": links_by_asset}
    except Exception as exc:  # noqa: BLE001
        log(f"!!! Visual Linking Failed: {exc}")
        _progress(state, "visual_linking", {"error": str(exc)}, status="error")
        return {**state, "error": str(exc)}


def node_imagination(state: IngestionState) -> IngestionState:
    if state.get("error"):
        return state
    try:
        log("--- Node: Imagination Synthesis ---")
        policy_sections = state.get("policy_sections") or []
        policy_clauses = state.get("policy_clauses") or []
        visual_rows = state.get("visual_rows") or []

        visual_ids = [v.get("visual_asset_id") for v in visual_rows if v.get("visual_asset_id")]
        visual_briefs_by_id: Dict[str, Dict[str, Any]] = {}
        if visual_ids:
            visual_meta_rows = _db_fetch_all(
                """
                SELECT id, asset_type, page_number, metadata
                FROM visual_assets
                WHERE id = ANY(%s::uuid[])
                """,
                (visual_ids,),
            )
            for row in visual_meta_rows:
                visual_id = str(row.get("id"))
                metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                visual_briefs_by_id[visual_id] = {
                    "asset_id": visual_id,
                    "asset_type": row.get("asset_type"),
                    "page_number": row.get("page_number"),
                    "caption": metadata.get("caption"),
                    "classification": metadata.get("classification") or {},
                    "rich_enrichment": metadata.get("rich_enrichment") or {},
                }

            semantic_rows = _db_fetch_all(
                """
                SELECT visual_asset_id, asset_type, asset_subtype, canonical_facts_jsonb, asset_specific_facts_jsonb
                FROM visual_semantic_outputs
                WHERE visual_asset_id = ANY(%s::uuid[])
                ORDER BY created_at DESC
                """,
                (visual_ids,),
            )
            for row in semantic_rows:
                visual_id = str(row.get("visual_asset_id"))
                entry = visual_briefs_by_id.setdefault(
                    visual_id,
                    {
                        "asset_id": visual_id,
                        "asset_type": row.get("asset_type"),
                        "asset_subtype": row.get("asset_subtype"),
                    },
                )
                entry["canonical_facts"] = row.get("canonical_facts_jsonb") or {}
                entry["asset_specific_facts"] = row.get("asset_specific_facts_jsonb") or {}

        clauses_by_section: Dict[str, List[Dict[str, Any]]] = {}
        for clause in policy_clauses:
            section_id = clause.get("policy_section_id")
            if not section_id:
                continue
            clauses_by_section.setdefault(section_id, []).append(
                {
                    "clause_ref": clause.get("clause_ref"),
                    "text": clause.get("text"),
                }
            )

        policy_briefs = [
            {
                "policy_code": s.get("policy_code"),
                "title": s.get("title"),
                "summary": (s.get("text") or "")[:800],
                "clause_snippets": clauses_by_section.get(s.get("policy_section_id"), [])[:6],
            }
            for s in policy_sections
        ]
        if not policy_briefs and policy_clauses:
            policy_briefs = [
                {
                    "policy_code": c.get("policy_code"),
                    "clause_ref": c.get("clause_ref"),
                    "text": (c.get("text") or "")[:600],
                }
                for c in policy_clauses[:120]
            ]

        visual_briefs = list(visual_briefs_by_id.values())

        synthesis = _llm_imagination_synthesis(state["document_id"], policy_briefs, visual_briefs, state.get("run_id"))
        _db_execute(
            "UPDATE documents SET metadata = metadata || %s::jsonb WHERE id = %s::uuid",
            (json.dumps({"imagination_synthesis": synthesis}, ensure_ascii=False), state["document_id"]),
        )
        _mark_step(state, "imagination_synthesis")
        _progress(state, "imagination_synthesis", {"linked": len(synthesis.get("cross_modal_links", []))})
        return state
    except Exception as exc:  # noqa: BLE001
        log(f"!!! Imagination Failed: {exc}")
        _progress(state, "imagination_synthesis", {"error": str(exc)}, status="error")
        return {**state, "error": str(exc)}


def node_embeddings(state: IngestionState) -> IngestionState:
    if state.get("error"):
        return state
    try:
        log("--- Node: Embeddings ---")
        chunk_rows = state.get("chunk_rows") or []
        policy_sections = state.get("policy_sections") or []
        policy_clauses = state.get("policy_clauses") or []
        visual_rows = state.get("visual_rows") or []

        _bump(
            state,
            "unit_embeddings_chunk",
            _embed_units(
                ingest_batch_id=state["ingest_batch_id"],
                run_id=state.get("run_id"),
                unit_type="chunk",
                rows=chunk_rows,
                text_key="text",
                id_key="chunk_id",
            ),
        )
        _bump(
            state,
            "unit_embeddings_policy_section",
            _embed_units(
                ingest_batch_id=state["ingest_batch_id"],
                run_id=state.get("run_id"),
                unit_type="policy_section",
                rows=policy_sections,
                text_key="text",
                id_key="policy_section_id",
            ),
        )
        _bump(
            state,
            "unit_embeddings_policy_clause",
            _embed_units(
                ingest_batch_id=state["ingest_batch_id"],
                run_id=state.get("run_id"),
                unit_type="policy_clause",
                rows=policy_clauses,
                text_key="text",
                id_key="policy_clause_id",
            ),
        )

        if visual_rows:
            _bump(
                state,
                "unit_embeddings_visual",
                _embed_visual_assets(
                    ingest_batch_id=state["ingest_batch_id"],
                    run_id=state.get("run_id"),
                    visual_assets=visual_rows,
                    policy_sections=policy_sections,
                    links_by_asset=state.get("links_by_asset") or {},
                ),
            )

        if state.get("counts", {}).get("visual_semantic_assertions", 0) > 0:
            _bump(
                state,
                "unit_embeddings_visual_assertion",
                _embed_visual_assertions(
                    ingest_batch_id=state["ingest_batch_id"],
                    run_id=state.get("run_id"),
                ),
            )
            _mark_step(state, "visual_assertion_embeddings")
            _progress(
                state,
                "visual_assertion_embeddings",
                {"unit_embeddings_visual_assertion": state["counts"].get("unit_embeddings_visual_assertion", 0)},
            )

        _mark_step(state, "embeddings")
        _mark_step(state, "visual_embeddings")
        _progress(
            state,
            "embeddings",
            {
                "unit_embeddings_chunk": state["counts"].get("unit_embeddings_chunk", 0),
                "unit_embeddings_policy_section": state["counts"].get("unit_embeddings_policy_section", 0),
                "unit_embeddings_policy_clause": state["counts"].get("unit_embeddings_policy_clause", 0),
            },
        )
        _progress(
            state,
            "visual_embeddings",
            {
                "unit_embeddings_visual": state["counts"].get("unit_embeddings_visual", 0),
            },
        )

        return state
    except Exception as exc:  # noqa: BLE001
        log(f"!!! Embeddings Failed: {exc}")
        _progress(state, "embeddings", {"error": str(exc)}, status="error")
        return {**state, "error": str(exc)}


def build_ingestion_graph(checkpointer=None, *, mode: str = "full"):
    workflow = StateGraph(IngestionState)

    workflow.add_node("anchor_raw", node_anchor_raw)
    workflow.add_node("docparse", node_docparse)
    workflow.add_node("canonical_load", node_canonical_load)

    workflow.set_entry_point("anchor_raw")
    workflow.add_edge("anchor_raw", "docparse")
    workflow.add_edge("docparse", "canonical_load")

    if mode == "cpu_only":
        workflow.add_edge("canonical_load", END)
    else:
        workflow.add_node("visual_pipeline", node_visual_pipeline)
        workflow.add_node("document_identity", node_document_identity)
        workflow.add_node("structural_llm", node_structural_llm)
        workflow.add_node("visual_linking", node_visual_linking)
        workflow.add_node("imagination", node_imagination)
        workflow.add_node("embeddings", node_embeddings)

        workflow.add_edge("canonical_load", "visual_pipeline")
        workflow.add_edge("visual_pipeline", "document_identity")
        workflow.add_edge("document_identity", "structural_llm")
        workflow.add_edge("structural_llm", "visual_linking")
        workflow.add_edge("visual_linking", "imagination")
        workflow.add_edge("imagination", "embeddings")
        workflow.add_edge("embeddings", END)

    return workflow.compile(checkpointer=checkpointer or MemorySaver())
