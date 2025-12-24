from __future__ import annotations

import json
from uuid import uuid4
from typing import Any

from tpa_api.db import _db_execute
from tpa_api.time_utils import _utc_now
from tpa_api.evidence import _ensure_evidence_ref_row, _parse_evidence_ref

# Functions moved from ingest_worker.py
def _persist_pages(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    pages: list[dict[str, Any]],
) -> None:
    for page in pages:
        page_number = int(page.get("page_number") or 0)
        if page_number <= 0:
            continue
        render_blob_path = page.get("render_blob_path")
        render_format = page.get("render_format")
        render_dpi = page.get("render_dpi")
        render_width = page.get("render_width")
        render_height = page.get("render_height")
        render_tier = page.get("render_tier")
        render_reason = page.get("render_reason")
        metadata: dict[str, Any] = {}
        for key in ("width", "height", "text_source", "text_source_reason"):
            if key in page:
                metadata[key] = page.get(key)
        _db_execute(
            """
            INSERT INTO pages (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              render_blob_path, render_format, render_dpi, render_width, render_height,
              render_tier, render_reason, metadata
            )
            VALUES (
              %s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid,
              %s, %s, %s, %s, %s,
              %s, %s, %s::jsonb
            )
            ON CONFLICT (document_id, page_number) DO NOTHING
            """,
            (
                str(uuid4()),
                document_id,
                page_number,
                ingest_batch_id,
                run_id,
                source_artifact_id,
                render_blob_path,
                render_format,
                render_dpi,
                render_width,
                render_height,
                render_tier,
                render_reason,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )


def _persist_bundle_evidence_refs(
    *,
    run_id: str | None,
    evidence_refs: list[dict[str, Any]],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for ref in evidence_refs:
        if not isinstance(ref, dict):
            continue
        source_doc_id = ref.get("source_doc_id")
        section_ref = ref.get("section_ref")
        if not isinstance(source_doc_id, str) or not isinstance(section_ref, str):
            continue
        evidence_ref = f"doc::{source_doc_id}::{section_ref}"
        locator_type = "figure" if section_ref.startswith("visual::") else "paragraph"
        locator_value = section_ref
        evidence_ref_id = _ensure_evidence_ref_row(
            evidence_ref,
            run_id=run_id,
            document_id=source_doc_id,
            locator_type=locator_type,
            locator_value=locator_value,
            excerpt=ref.get("snippet_text"),
        )
        if evidence_ref_id:
            mapping[section_ref] = evidence_ref_id
    return mapping


def _find_span(text: str, fragment: str) -> tuple[int | None, int | None, str]:
    if not text or not fragment:
        return None, None, "none"
    idx = text.find(fragment)
    if idx >= 0:
        return idx, idx + len(fragment), "exact"
    lowered = text.lower()
    frag_lower = fragment.lower()
    idx = lowered.find(frag_lower)
    if idx >= 0:
        return idx, idx + len(fragment), "approx"
    return None, None, "none"


def _find_trigger_spans(text: str, fragment: str) -> list[dict[str, Any]]:
    if not text or not fragment:
        return []
    spans: list[dict[str, Any]] = []
    idx = text.find(fragment)
    if idx >= 0:
        spans.append({"start": idx, "end": idx + len(fragment), "quality": "exact"})
    if spans:
        return spans
    lowered = text.lower()
    frag_lower = fragment.lower()
    start = 0
    while True:
        idx = lowered.find(frag_lower, start)
        if idx < 0:
            break
        spans.append({"start": idx, "end": idx + len(fragment), "quality": "approx"})
        start = idx + len(fragment)
    return spans


def _persist_layout_blocks(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    pages: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    evidence_ref_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    page_texts = {int(p.get("page_number") or 0): str(p.get("text") or "") for p in pages}
    rows: list[dict[str, Any]] = []
    evidence_ref_map = evidence_ref_map or {}
    for block in blocks:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        page_number = int(block.get("page_number") or 0)
        layout_block_id = str(uuid4())
        block_id = str(block.get("block_id") or layout_block_id)
        span_start, span_end, span_quality = _find_span(page_texts.get(page_number, ""), text)
        evidence_ref_id: str | None = None
        used_external_ref = False
        raw_ref = block.get("evidence_ref")
        if isinstance(raw_ref, str):
            parsed = _parse_evidence_ref(raw_ref)
            if parsed:
                evidence_ref_id = evidence_ref_map.get(parsed[2])
                if evidence_ref_id:
                    used_external_ref = True
                else:
                    evidence_ref_id = _ensure_evidence_ref_row(raw_ref, run_id=run_id)
                    used_external_ref = bool(evidence_ref_id)
        if not evidence_ref_id:
            evidence_ref_id = str(uuid4())
        metadata = {}
        raw_meta = block.get("metadata") if isinstance(block.get("metadata"), dict) else {}
        if raw_meta:
            metadata.update(raw_meta)
        if "text_source" in block:
            metadata.setdefault("text_source", block.get("text_source"))
        if "text_source_reason" in block:
            metadata.setdefault("text_source_reason", block.get("text_source_reason"))

        _db_execute(
            """
            INSERT INTO layout_blocks (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              block_id, block_type, text, bbox, bbox_quality, section_path,
              span_start, span_end, span_quality, evidence_ref_id, metadata_jsonb
            )
            VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s::uuid, %s::jsonb)
            """,
            (
                layout_block_id,
                document_id,
                page_number,
                ingest_batch_id,
                run_id,
                source_artifact_id,
                block_id,
                block.get("type") or "unknown",
                text,
                json.dumps(block.get("bbox"), ensure_ascii=False) if block.get("bbox") is not None else None,
                block.get("bbox_quality"),
                block.get("section_path"),
                span_start,
                span_end,
                span_quality,
                evidence_ref_id,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        if not used_external_ref:
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (evidence_ref_id, "layout_block", layout_block_id, block_id, run_id),
            )
        evidence_ref_str = raw_ref if isinstance(raw_ref, str) else f"layout_block::{layout_block_id}::{block_id}"
        rows.append(
            {
                "layout_block_id": layout_block_id,
                "block_id": block_id,
                "page_number": page_number,
                "text": text,
                "type": block.get("type"),
                "section_path": block.get("section_path"),
                "bbox": block.get("bbox"),
                "bbox_quality": block.get("bbox_quality"),
                "span_start": span_start,
                "span_end": span_end,
                "span_quality": span_quality,
                "evidence_ref_id": evidence_ref_id,
                "evidence_ref": evidence_ref_str,
            }
        )
    return rows


def _persist_document_tables(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    tables: list[dict[str, Any]],
) -> None:
    for table in tables:
        table_id = str(table.get("table_id") or uuid4())
        page_number = int(table.get("page_number") or 0)
        evidence_ref_id = str(uuid4())
        doc_table_id = str(uuid4())
        _db_execute(
            """
            INSERT INTO document_tables (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              table_id, bbox, bbox_quality, rows_jsonb, evidence_ref_id, metadata_jsonb
            )
            VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s::jsonb, %s::uuid, %s::jsonb)
            """,
            (
                doc_table_id,
                document_id,
                page_number,
                ingest_batch_id,
                run_id,
                source_artifact_id,
                table_id,
                json.dumps(table.get("bbox"), ensure_ascii=False) if table.get("bbox") is not None else None,
                table.get("bbox_quality"),
                json.dumps(table.get("rows") or [], ensure_ascii=False),
                evidence_ref_id,
                json.dumps({}, ensure_ascii=False),
            ),
        )
        _db_execute(
            "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
            (evidence_ref_id, "document_table", doc_table_id, "table", run_id),
        )


def _persist_vector_paths(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    vector_paths: list[dict[str, Any]],
) -> None:
    for path in vector_paths:
        path_id = str(path.get("path_id") or uuid4())
        page_number = int(path.get("page_number") or 0)
        _db_execute(
            """
            INSERT INTO vector_paths (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              path_id, path_type, geometry_jsonb, bbox, bbox_quality, tool_run_id, metadata_jsonb
            )
            VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s::jsonb, %s, %s::uuid, %s::jsonb)
            """,
            (
                str(uuid4()),
                document_id,
                page_number,
                ingest_batch_id,
                run_id,
                source_artifact_id,
                path_id,
                path.get("path_type") or "unknown",
                json.dumps(path.get("geometry"), ensure_ascii=False) if path.get("geometry") is not None else None,
                json.dumps(path.get("bbox"), ensure_ascii=False) if path.get("bbox") is not None else None,
                path.get("bbox_quality"),
                None,
                json.dumps({}, ensure_ascii=False),
            ),
        )


def _persist_chunks_from_blocks(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    block_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    chunk_rows: list[dict[str, Any]] = []
    for block in block_rows:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        chunk_id = str(uuid4())
        page_number = block.get("page_number")
        fragment = str(block.get("block_id") or "block")
        evidence_ref_id = block.get("evidence_ref_id")
        if not evidence_ref_id:
            evidence_ref_id = str(uuid4())
        _db_execute(
            """
            INSERT INTO chunks (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              text, bbox, bbox_quality, type, section_path, span_start, span_end,
              span_quality, evidence_ref_id, metadata
            )
            VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s::uuid, %s::jsonb)
            """,
            (
                chunk_id,
                document_id,
                page_number,
                ingest_batch_id,
                run_id,
                source_artifact_id,
                text,
                json.dumps(block.get("bbox"), ensure_ascii=False) if block.get("bbox") is not None else None,
                block.get("bbox_quality"),
                block.get("type"),
                block.get("section_path"),
                block.get("span_start"),
                block.get("span_end"),
                block.get("span_quality"),
                evidence_ref_id,
                json.dumps({"evidence_ref_fragment": fragment}, ensure_ascii=False),
            ),
        )
        if evidence_ref_id and not block.get("evidence_ref_id"):
            _db_execute(
                "INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id) VALUES (%s, %s, %s, %s, %s::uuid)",
                (evidence_ref_id, "chunk", chunk_id, fragment, run_id),
            )
        chunk_rows.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "page_number": page_number,
                "fragment": fragment,
                "evidence_ref": block.get("evidence_ref") or f"chunk::{chunk_id}::{fragment}",
                "type": block.get("type"),
                "section_path": block.get("section_path"),
                "span_start": block.get("span_start"),
                "span_end": block.get("span_end"),
                "evidence_ref_id": evidence_ref_id,
            }
        )
    return chunk_rows


def _persist_visual_assets(
    *,
    document_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    source_artifact_id: str | None,
    visual_assets: list[dict[str, Any]],
    evidence_ref_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    evidence_ref_map = evidence_ref_map or {}
    for asset in visual_assets:
        asset_id = str(uuid4())
        blob_path = asset.get("blob_path")
        if not isinstance(blob_path, str) or not blob_path:
            continue
        metadata = {
            "asset_type": asset.get("asset_type"),
            "role": asset.get("role"),
            "classification": asset.get("classification") or {},
            "metrics": asset.get("metrics") or [],
            "caption": asset.get("caption"),
            "width": asset.get("width"),
            "height": asset.get("height"),
            "source_asset_id": asset.get("asset_id"),
        }
        now = _utc_now()
        evidence_ref_id: str | None = None
        source_asset_id = asset.get("asset_id")
        if isinstance(source_asset_id, str) and source_asset_id:
            fragment = f"visual::{source_asset_id}"
            evidence_ref_id = evidence_ref_map.get(fragment)
            if not evidence_ref_id:
                evidence_ref = f"doc::{document_id}::{fragment}"
                evidence_ref_id = _ensure_evidence_ref_row(evidence_ref, run_id=run_id)
            if not evidence_ref_id:
                evidence_ref_id = str(uuid4())
                _db_execute(
                    """
                    INSERT INTO evidence_refs (id, source_type, source_id, fragment_id, run_id)
                    VALUES (%s, %s, %s, %s, %s::uuid)
                    """,
                    (evidence_ref_id, "visual_asset", asset_id, "image", run_id),
                )
        _db_execute(
            """
            INSERT INTO visual_assets (
              id, document_id, page_number, ingest_batch_id, run_id, source_artifact_id,
              asset_type, blob_path, evidence_ref_id, metadata, created_at, updated_at
            )
            VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s::uuid, %s::jsonb, %s, %s)
            """,
            (
                asset_id,
                document_id,
                asset.get("page_number"),
                ingest_batch_id,
                run_id,
                source_artifact_id,
                asset.get("asset_type") or "unknown",
                blob_path,
                evidence_ref_id,
                json.dumps(metadata, ensure_ascii=False),
                now,
                now,
            ),
        )
        rows.append(
            {
                "visual_asset_id": asset_id,
                "document_id": document_id,
                "page_number": asset.get("page_number"),
                "metadata": metadata,
                "blob_path": blob_path,
                "evidence_ref_id": evidence_ref_id,
                "source_asset_id": asset.get("asset_id"),
            }
        )
    return rows


def _persist_visual_features(*, visual_assets: list[dict[str, Any]], run_id: str | None) -> None:
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        if not visual_asset_id:
            continue
        metadata = asset.get("metadata") or {}
        classification = metadata.get("classification") or {}
        feature_type = classification.get("asset_type") or "visual_classification"
        _db_execute(
            """
            INSERT INTO visual_features (
              id, visual_asset_id, run_id, feature_type,
              geometry_jsonb, confidence, evidence_ref_id, metadata_jsonb
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s::uuid, %s::jsonb)
            """,
            (
                str(uuid4()),
                visual_asset_id,
                run_id,
                feature_type,
                None,
                None,
                asset.get("evidence_ref_id"),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )


def _persist_visual_semantic_features(
    *,
    visual_assets: list[dict[str, Any]],
    semantic: dict[str, Any],
    run_id: str | None,
) -> None:
    if not semantic:
        return
    blob_map = {row.get("blob_path"): row for row in visual_assets if row.get("blob_path")}

    constraints = semantic.get("visual_constraints") if isinstance(semantic.get("visual_constraints"), list) else []
    for vc in constraints:
        if not isinstance(vc, dict):
            continue
        image_ref = vc.get("image_ref")
        row = blob_map.get(image_ref)
        if not row:
            continue
        _db_execute(
            """
            INSERT INTO visual_features (
              id, visual_asset_id, run_id, feature_type,
              geometry_jsonb, confidence, evidence_ref_id, metadata_jsonb
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s::uuid, %s::jsonb)
            """,
            (
                str(uuid4()),
                row.get("visual_asset_id"),
                run_id,
                "visual_constraint",
                None,
                None,
                row.get("evidence_ref_id"),
                json.dumps(vc, ensure_ascii=False),
            ),
        )


# Temporary re-exports for remaining functions
from tpa_api.ingest_worker import (
    _call_docparse_bundle,
    _load_parse_bundle,
    _insert_parse_bundle_record,
    _persist_tool_runs,
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
