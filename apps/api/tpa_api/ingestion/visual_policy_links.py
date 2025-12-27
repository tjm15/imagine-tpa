from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from tpa_api.db import _db_execute, _db_fetch_all, _db_fetch_one
from tpa_api.prompting import _llm_structured_sync
from tpa_api.time_utils import _utc_now


def _truncate_text(text: str | None, limit: int) -> str:
    if not isinstance(text, str):
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _persist_visual_rich_enrichment(
    *,
    visual_asset_id: str,
    run_id: str | None,
    tool_run_id: str | None,
    enrichment: dict[str, Any] | None,
) -> dict[str, int]:
    if not enrichment or not visual_asset_id:
        return {"enrichments": 0, "layers": 0, "toponyms": 0, "policy_codes": 0}

    asset_category = enrichment.get("asset_category") if isinstance(enrichment.get("asset_category"), str) else None
    map_scale_declared = enrichment.get("map_scale_declared") if isinstance(enrichment.get("map_scale_declared"), str) else None
    orientation = enrichment.get("orientation") if isinstance(enrichment.get("orientation"), str) else None
    interpretation_notes = enrichment.get("interpretation_notes") if isinstance(enrichment.get("interpretation_notes"), str) else None
    legibility_score = enrichment.get("legibility_score") if isinstance(enrichment.get("legibility_score"), (int, float)) else None

    enrichment_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO visual_rich_enrichments (
          id, visual_asset_id, run_id, asset_category, map_scale_declared, orientation,
          legibility_score, interpretation_notes, tool_run_id, metadata_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s::uuid, %s::jsonb, %s)
        """,
        (
            enrichment_id,
            visual_asset_id,
            run_id,
            asset_category,
            map_scale_declared,
            orientation,
            float(legibility_score) if isinstance(legibility_score, (int, float)) else None,
            interpretation_notes,
            tool_run_id,
            json.dumps(enrichment, ensure_ascii=False),
            _utc_now(),
        ),
    )

    layer_count = 0
    layers = enrichment.get("detected_layers") if isinstance(enrichment.get("detected_layers"), list) else []
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        _db_execute(
            """
            INSERT INTO visual_rich_layers (
              id, enrichment_id, visual_asset_id, run_id, layer_name, layer_type,
              representation_style, color_hex_guess, is_legend_item, tool_run_id, metadata_jsonb, created_at
            )
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s::uuid, %s::jsonb, %s)
            """,
            (
                str(uuid4()),
                enrichment_id,
                visual_asset_id,
                run_id,
                layer.get("layer_name"),
                layer.get("layer_type"),
                layer.get("representation_style"),
                layer.get("color_hex_guess"),
                bool(layer.get("is_legend_item")),
                tool_run_id,
                json.dumps(layer, ensure_ascii=False),
                _utc_now(),
            ),
        )
        layer_count += 1

    toponym_count = 0
    toponyms = enrichment.get("extracted_toponyms") if isinstance(enrichment.get("extracted_toponyms"), list) else []
    for name in toponyms:
        if not isinstance(name, str) or not name.strip():
            continue
        _db_execute(
            """
            INSERT INTO visual_rich_toponyms (
              id, enrichment_id, visual_asset_id, run_id, name, tool_run_id, created_at
            )
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s::uuid, %s)
            """,
            (
                str(uuid4()),
                enrichment_id,
                visual_asset_id,
                run_id,
                name.strip(),
                tool_run_id,
                _utc_now(),
            ),
        )
        toponym_count += 1

    policy_code_count = 0
    policy_codes = enrichment.get("linked_policy_codes") if isinstance(enrichment.get("linked_policy_codes"), list) else []
    for code in policy_codes:
        if not isinstance(code, str) or not code.strip():
            continue
        _db_execute(
            """
            INSERT INTO visual_rich_policy_refs (
              id, enrichment_id, visual_asset_id, run_id, policy_code, tool_run_id, created_at
            )
            VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s, %s::uuid, %s)
            """,
            (
                str(uuid4()),
                enrichment_id,
                visual_asset_id,
                run_id,
                code.strip(),
                tool_run_id,
                _utc_now(),
            ),
        )
        policy_code_count += 1

    return {
        "enrichments": 1,
        "layers": layer_count,
        "toponyms": toponym_count,
        "policy_codes": policy_code_count,
    }


def _propose_visual_policy_links(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
    policy_sections: list[dict[str, Any]],
    page_texts: dict[int, str],
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    if not visual_assets or not policy_sections:
        return {}, 0

    candidates_all = [
        {
            "policy_section_id": s.get("policy_section_id"),
            "policy_code": s.get("policy_code"),
            "title": s.get("title"),
            "section_path": s.get("section_path"),
        }
        for s in policy_sections
        if s.get("policy_section_id")
    ]
    if not candidates_all:
        return {}, 0

    system_template = (
        "You are a planning visual linker. Return ONLY valid JSON with:\n"
        '{ "links": [ { "policy_section_id": "uuid", "confidence": "low|medium|high", '
        '"rationale": "string", "basis": "in_image_text|caption|visual_facts|page_context" } ] }\n'
        "Rules:\n"
        "- Only link to policy_section_id values provided in policy_candidates.\n"
        "- Use extracted text snippets if present. Do not invent policy codes.\n"
    )

    proposals_by_asset: dict[str, list[dict[str, Any]]] = {}
    proposal_count = 0

    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        if not visual_asset_id:
            continue
        metadata = asset.get("metadata") or {}
        page_number = int(asset.get("page_number") or 0)
        caption = metadata.get("caption") or (metadata.get("classification") or {}).get("caption_hint")
        page_text = _truncate_text(page_texts.get(page_number), 1200)

        semantic_row = _db_fetch_one(
            """
            SELECT asset_type, asset_subtype, canonical_facts_jsonb, asset_specific_facts_jsonb
            FROM visual_semantic_outputs
            WHERE visual_asset_id = %s::uuid
              AND (%s::uuid IS NULL OR run_id = %s::uuid)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (visual_asset_id, run_id, run_id),
        )
        asset_type = semantic_row.get("asset_type") if isinstance(semantic_row, dict) else None
        asset_subtype = semantic_row.get("asset_subtype") if isinstance(semantic_row, dict) else None
        canonical_facts = (
            semantic_row.get("canonical_facts_jsonb")
            if isinstance(semantic_row, dict) and isinstance(semantic_row.get("canonical_facts_jsonb"), dict)
            else {}
        )
        asset_specific = (
            semantic_row.get("asset_specific_facts_jsonb")
            if isinstance(semantic_row, dict) and isinstance(semantic_row.get("asset_specific_facts_jsonb"), dict)
            else {}
        )

        text_rows = _db_fetch_all(
            """
            SELECT caption_text
            FROM visual_asset_regions
            WHERE visual_asset_id = %s::uuid
              AND region_type = 'text_snippet'
              AND (%s::uuid IS NULL OR run_id = %s::uuid)
            ORDER BY created_at ASC
            LIMIT 25
            """,
            (visual_asset_id, run_id, run_id),
        )
        text_snippets = [r.get("caption_text") for r in text_rows if isinstance(r.get("caption_text"), str)]

        obj, tool_run_id, errs = _llm_structured_sync(
            prompt_id="visual_policy_link_v1",
            prompt_version=1,
            prompt_name="Visual policy linker",
            purpose="Link visual assets to policy sections using extracted text and asset facts.",
            system_template=system_template,
            user_payload={
                "visual_asset_id": visual_asset_id,
                "asset_type": asset_type,
                "asset_subtype": asset_subtype,
                "caption": caption,
                "page_text": page_text,
                "text_snippets": text_snippets,
                "canonical_facts": canonical_facts,
                "asset_specific_facts": asset_specific,
                "policy_candidates": candidates_all,
            },
            output_schema_ref=None,
            ingest_batch_id=ingest_batch_id,
            run_id=run_id,
        )
        if errs or not isinstance(obj, dict):
            raise RuntimeError(f"visual_link_failed:{errs or 'invalid_response'}")

        links = obj.get("links")
        if not isinstance(links, list):
            continue
        for link in links:
            if not isinstance(link, dict):
                continue
            policy_section_id = link.get("policy_section_id")
            if not isinstance(policy_section_id, str):
                continue
            proposals_by_asset.setdefault(visual_asset_id, []).append(
                {
                    "policy_section_id": policy_section_id,
                    "confidence": link.get("confidence"),
                    "rationale": link.get("rationale"),
                    "basis": link.get("basis") or "unspecified",
                    "page_number": page_number,
                    "tool_run_id": tool_run_id,
                }
            )
            proposal_count += 1

    return proposals_by_asset, proposal_count


def _persist_visual_policy_links_from_proposals(
    *,
    run_id: str | None,
    proposals_by_asset: dict[str, list[dict[str, Any]]],
    visual_assets: list[dict[str, Any]],
    policy_sections: list[dict[str, Any]],
) -> tuple[dict[str, list[str]], int]:
    if not proposals_by_asset:
        return {}, 0
    section_by_id = {str(s.get("policy_section_id")): s for s in policy_sections if s.get("policy_section_id")}
    section_by_code = {
        str(s.get("policy_code")).strip(): s
        for s in policy_sections
        if isinstance(s.get("policy_code"), str)
    }
    section_by_title = {
        str(s.get("title")).strip().lower(): s
        for s in policy_sections
        if isinstance(s.get("title"), str)
    }
    evidence_by_asset = {row.get("visual_asset_id"): row.get("evidence_ref_id") for row in visual_assets}
    links_by_asset: dict[str, list[str]] = {}
    link_count = 0

    for asset_id, proposals in proposals_by_asset.items():
        for link in proposals:
            policy_section_id = link.get("policy_section_id")
            policy_code = link.get("policy_code")
            section = None
            if isinstance(policy_section_id, str):
                section = section_by_id.get(policy_section_id)
            if isinstance(policy_code, str):
                section = section_by_code.get(policy_code.strip()) or section_by_code.get(policy_code.strip().upper())
                if not section:
                    section = section_by_title.get(policy_code.strip().lower())
            if not section:
                continue
            section_id = section.get("policy_section_id")
            if not section_id:
                continue
            _db_execute(
                """
                INSERT INTO visual_asset_links (
                  id, visual_asset_id, run_id, target_type, target_id, link_type,
                  evidence_ref_id, tool_run_id, metadata_jsonb, created_at
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s::uuid, %s::uuid, %s::jsonb, %s)
                """,
                (
                    str(uuid4()),
                    asset_id,
                    run_id,
                    "policy_section",
                    str(section_id),
                    "policy_reference",
                    evidence_by_asset.get(asset_id),
                    link.get("tool_run_id"),
                    json.dumps(
                        {
                            "policy_code": section.get("policy_code"),
                            "policy_title": section.get("title"),
                            "confidence": link.get("confidence"),
                            "rationale": link.get("rationale"),
                            "basis": link.get("basis") or "unspecified",
                            "candidate_scope": link.get("candidate_scope") or "all",
                            "page_number": link.get("page_number"),
                        },
                        ensure_ascii=False,
                    ),
                    _utc_now(),
                ),
            )
            links_by_asset.setdefault(asset_id, []).append(str(section_id))
            link_count += 1

    return links_by_asset, link_count
