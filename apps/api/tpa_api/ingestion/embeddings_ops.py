from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID, uuid4

from tpa_api.blob_store import read_blob_bytes
from tpa_api.db import _db_execute, _db_fetch_all
from tpa_api.model_clients import _embed_multimodal_sync, _embed_texts_sync
from tpa_api.time_utils import _utc_now
from tpa_api.vector_utils import _vector_literal


def _truncate_text(text: str | None, limit: int) -> str:
    if not isinstance(text, str):
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _embed_visual_assets(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
    policy_sections: list[dict[str, Any]],
    links_by_asset: dict[str, list[str]],
) -> int:
    if not visual_assets:
        return 0
    model_id = os.environ.get("TPA_EMBEDDINGS_MM_MODEL_ID", "nomic-ai/colnomic-embed-multimodal-7b")
    tool_run_id = str(uuid4())
    started = _utc_now()
    _db_execute(
        """
        INSERT INTO tool_runs (
          id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
          started_at, ended_at, confidence_hint, uncertainty_note
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, %s, %s)
        """,
        (
            tool_run_id,
            ingest_batch_id,
            run_id,
            "embed_visual_assets",
            json.dumps({"asset_count": len(visual_assets), "model_id": model_id}, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
            "running",
            started,
            "medium",
            "Embedding visual assets with policy-linked context.",
        ),
    )

    sections_by_id = {s.get("policy_section_id"): s for s in policy_sections if s.get("policy_section_id")}
    inserted = 0
    skipped = 0
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        blob_path = asset.get("blob_path")
        if not visual_asset_id or not isinstance(blob_path, str):
            continue
        linked = links_by_asset.get(visual_asset_id) or []
        if not linked:
            skipped += 1
            continue
        image_bytes, _, err = read_blob_bytes(blob_path)
        if err or not image_bytes:
            raise RuntimeError(f"visual_asset_read_failed:{err or 'no_bytes'}")

        metadata = asset.get("metadata") or {}
        caption = metadata.get("caption") or (metadata.get("classification") or {}).get("caption_hint")
        context_lines = []
        if caption:
            context_lines.append(f"Caption: {caption}")
        if metadata.get("asset_type"):
            context_lines.append(f"Asset type: {metadata.get('asset_type')}")
        for section_id in linked:
            section = sections_by_id.get(section_id) or {}
            code = section.get("policy_code") or "policy"
            title = section.get("title") or ""
            context_lines.append(f"Policy {code}: {title}".strip())
            context_lines.append(_truncate_text(section.get("text"), 800))
        context_text = "\n".join([line for line in context_lines if line]).strip()
        if not context_text:
            skipped += 1
            continue

        vec = _embed_multimodal_sync(image_bytes=image_bytes, text=context_text, model_id=model_id)
        if not vec:
            _db_execute(
                "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
                (
                    "error",
                    json.dumps({"error": "visual_embedding_failed", "visual_asset_id": visual_asset_id}, ensure_ascii=False),
                    _utc_now(),
                    tool_run_id,
                ),
            )
            raise RuntimeError("visual_embedding_failed")

        _db_execute(
            """
            INSERT INTO unit_embeddings (
              id, unit_type, unit_id, embedding, embedding_model_id, embedding_dim, created_at, tool_run_id, run_id
            )
            VALUES (%s, %s, %s::uuid, %s::vector, %s, %s, %s, %s::uuid, %s::uuid)
            ON CONFLICT (unit_type, unit_id, embedding_model_id) DO NOTHING
            """,
            (
                str(uuid4()),
                "visual_asset",
                visual_asset_id,
                _vector_literal(vec),
                model_id,
                len(vec),
                _utc_now(),
                tool_run_id,
                run_id,
            ),
        )
        inserted += 1

    _db_execute(
        "UPDATE tool_runs SET status = %s, outputs_logged = %s::jsonb, ended_at = %s WHERE id = %s::uuid",
        (
            "success" if inserted > 0 or skipped > 0 else "error",
            json.dumps({"inserted": inserted, "skipped": skipped}, ensure_ascii=False),
            _utc_now(),
            tool_run_id,
        ),
    )
    return inserted


def _embed_visual_assertions(*, ingest_batch_id: str, run_id: str | None) -> int:
    rows = _db_fetch_all(
        """
        SELECT id, assertions_jsonb
        FROM visual_semantic_outputs
        WHERE (%s::uuid IS NULL OR run_id = %s::uuid)
        """,
        (run_id, run_id),
    )
    candidates: list[tuple[str, str]] = []
    for row in rows:
        assertions = row.get("assertions_jsonb") if isinstance(row.get("assertions_jsonb"), list) else []
        for assertion in assertions:
            if not isinstance(assertion, dict):
                continue
            assertion_id = assertion.get("assertion_id")
            statement = assertion.get("statement")
            if not isinstance(assertion_id, str) or not isinstance(statement, str) or not statement.strip():
                continue
            try:
                UUID(assertion_id)
            except Exception:  # noqa: BLE001
                continue
            candidates.append((assertion_id, statement.strip()))
    if not candidates:
        return 0

    texts = [text for _, text in candidates]
    embeddings = _embed_texts_sync(texts=texts, model_id=os.environ.get("TPA_EMBEDDINGS_MODEL_ID"))
    if not embeddings:
        return 0

    tool_run_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO tool_runs (
          id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
          started_at, ended_at, confidence_hint, uncertainty_note
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
        """,
        (
            tool_run_id,
            ingest_batch_id,
            run_id,
            "embed_visual_assertions",
            json.dumps({"assertion_count": len(embeddings)}, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
            "running",
            _utc_now(),
            None,
            "medium",
            "Embedding visual assertions for retrieval.",
        ),
    )

    inserted = 0
    for (assertion_id, _), vec in zip(candidates, embeddings, strict=True):
        _db_execute(
            """
            INSERT INTO unit_embeddings (
              id, unit_type, unit_id, embedding, embedding_model_id, embedding_dim, created_at, tool_run_id, run_id
            )
            VALUES (%s, %s, %s::uuid, %s::vector, %s, %s, %s, %s::uuid, %s::uuid)
            ON CONFLICT (unit_type, unit_id, embedding_model_id) DO NOTHING
            """,
            (
                str(uuid4()),
                "visual_assertion",
                assertion_id,
                _vector_literal(vec),
                os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B"),
                len(vec) if isinstance(vec, list) else None,
                _utc_now(),
                tool_run_id,
                run_id,
            ),
        )
        inserted += 1

    _db_execute(
        """
        UPDATE tool_runs
        SET status = %s, outputs_logged = %s::jsonb, ended_at = %s
        WHERE id = %s::uuid
        """,
        (
            "success" if inserted > 0 else "error",
            json.dumps({"inserted": inserted}, ensure_ascii=False),
            _utc_now(),
            tool_run_id,
        ),
    )
    return inserted


def _embed_units(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    unit_type: str,
    rows: list[dict[str, Any]],
    text_key: str,
    id_key: str,
) -> int:
    candidates = [
        (r.get(id_key), r.get(text_key))
        for r in rows
        if isinstance(r.get(text_key), str) and r.get(text_key).strip() and r.get(id_key)
    ]
    if not candidates:
        return 0
    texts = [text for _, text in candidates]
    embeddings = _embed_texts_sync(texts=texts, model_id=os.environ.get("TPA_EMBEDDINGS_MODEL_ID"))
    if not embeddings:
        return 0
    tool_run_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO tool_runs (
          id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
          started_at, ended_at, confidence_hint, uncertainty_note
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
        """,
        (
            tool_run_id,
            ingest_batch_id,
            run_id,
            "embed_units",
            json.dumps({"unit_type": unit_type, "unit_count": len(embeddings)}, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
            "running",
            _utc_now(),
            None,
            "medium",
            "Embedding units for retrieval.",
        ),
    )
    inserted = 0
    for (unit_id, _), vec in zip(candidates, embeddings, strict=True):
        _db_execute(
            """
            INSERT INTO unit_embeddings (
              id, unit_type, unit_id, embedding, embedding_model_id, embedding_dim, created_at, tool_run_id, run_id
            )
            VALUES (%s, %s, %s::uuid, %s::vector, %s, %s, %s, %s::uuid, %s::uuid)
            ON CONFLICT (unit_type, unit_id, embedding_model_id) DO NOTHING
            """,
            (
                str(uuid4()),
                unit_type,
                unit_id,
                _vector_literal(vec),
                os.environ.get("TPA_EMBEDDINGS_MODEL_ID", "Qwen/Qwen3-Embedding-8B"),
                len(vec) if isinstance(vec, list) else None,
                _utc_now(),
                tool_run_id,
                run_id,
            ),
        )
        inserted += 1
    _db_execute(
        """
        UPDATE tool_runs
        SET status = %s, outputs_logged = %s::jsonb, ended_at = %s
        WHERE id = %s::uuid
        """,
        (
            "success" if inserted > 0 else "error",
            json.dumps({"inserted": inserted, "unit_type": unit_type}, ensure_ascii=False),
            _utc_now(),
            tool_run_id,
        ),
    )
    return inserted
