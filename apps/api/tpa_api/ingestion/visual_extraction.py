from __future__ import annotations

import json
import logging
import os
import random
import time
from pathlib import Path
from uuid import uuid4, UUID
from typing import Any

from tpa_api.db import _db_execute, _db_fetch_one, _db_fetch_all
from tpa_api.time_utils import _utc_now
from tpa_api.providers.factory import get_vlm_provider, get_blob_store_provider, get_segmentation_provider
from tpa_api.services.prompts import PromptService
from tpa_api.evidence import _ensure_evidence_ref_row
from tpa_api.ingestion.vectorization import _bbox_from_geometry
from tpa_api.ingestion.policy_extraction import run_llm_prompt # Reusing helper logic or duplication? Duplication is safer for decoupling.
from tpa_api.text_utils import _extract_json_object
from jsonschema import validate as _validate_schema
from jsonschema import ValidationError

logger = logging.getLogger(__name__)


def _load_schema_ref(schema_ref: str | dict[str, Any] | None) -> dict[str, Any] | None:
    if not schema_ref:
        return None
    if isinstance(schema_ref, dict):
        return schema_ref
    base = Path(__file__).resolve()
    root = None
    for parent in base.parents:
        if (parent / "schemas").is_dir() or (parent / "spec" / "schemas").is_dir():
            root = parent
            break
    if root is None:
        root = base.parent
    schema_path = root / schema_ref
    if not schema_path.is_file():
        schema_path = root / "schemas" / schema_ref
    if not schema_path.is_file():
        schema_path = root / "spec" / schema_ref
    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema not found: {schema_ref}")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _run_vlm_prompt(
    prompt_id: str,
    prompt_version: int,
    prompt_name: str,
    purpose: str,
    system_template: str | None, # VLM prompts are often just user text + image
    user_text: str,
    image_bytes: bytes,
    output_schema: str | None = None,
    run_id: str | None = None,
    ingest_batch_id: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """
    Helper to run VLM via Provider + PromptService.
    """
    max_attempts = 3
    base_delay_seconds = 2.0
    prompt_svc = PromptService()
    template_to_store = f"SYSTEM: {system_template}\nUSER: {user_text}" if system_template else user_text
    
    prompt_svc.register_prompt(
        prompt_id=prompt_id,
        version=prompt_version,
        name=prompt_name,
        purpose=purpose,
        template=template_to_store,
        output_schema={"ref": output_schema} if output_schema else None
    )
    
    provider = get_vlm_provider()
    
    messages = []
    if system_template:
        messages.append({"role": "system", "content": system_template})
    messages.append({"role": "user", "content": user_text})
    
    errors: list[str] = []
    last_tool_run_id: str | None = None
    use_response_format = True
    temperature = float(os.environ.get("TPA_VLM_TEMPERATURE", "0.3"))
    schema_obj = _load_schema_ref(output_schema)
    for attempt in range(1, max_attempts + 1):
        try:
            options = {
                "run_id": run_id,
                "ingest_batch_id": ingest_batch_id,
                "temperature": temperature,
                "attempt": attempt,
                "max_attempts": max_attempts,
            }
            if use_response_format:
                if schema_obj:
                    schema_name = schema_obj.get("title") or "StructuredOutput"
                    options["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_name,
                            "schema": schema_obj,
                            "strict": True,
                        },
                    }
                else:
                    options["response_format"] = {"type": "json_object"}
            result = provider.generate_structured(
                messages=messages,
                images=[image_bytes],
                json_schema=schema_obj,
                options=options,
            )
            last_tool_run_id = result.get("tool_run_id")
            payload = result.get("json")
            if not isinstance(payload, dict):
                raw_text = result.get("raw_text")
                if isinstance(raw_text, str) and raw_text.strip():
                    payload = _extract_json_object(raw_text)
            if isinstance(payload, dict):
                if schema_obj:
                    try:
                        _validate_schema(payload, schema_obj)
                        return payload, last_tool_run_id, []
                    except ValidationError as exc:
                        errors.append(f"vlm_schema_validation_failed:attempt={attempt}:{exc.message}")
                else:
                    return payload, last_tool_run_id, []
            errors.append(f"vlm_json_parse_failed:attempt={attempt}")
        except Exception as exc:
            err_text = str(exc)
            if use_response_format and "response_format" in err_text.lower():
                use_response_format = False
            errors.append(f"attempt={attempt}:{err_text}")
            logger.warning("VLM prompt %s failed on attempt %s/%s: %s", prompt_id, attempt, max_attempts, err_text)
        if attempt < max_attempts:
            delay = base_delay_seconds * (2 ** (attempt - 1))
            delay += random.random() * 0.6
            logger.info("Retrying VLM prompt %s in %.1fs", prompt_id, delay)
            time.sleep(delay)
    return None, last_tool_run_id, errors


def _upsert_visual_semantic_output(
    *,
    visual_asset_id: str,
    run_id: str | None,
    schema_version: str,
    output_kind: str = "classification",
    tool_run_id: str | None,
    asset_type: str | None = None,
    asset_subtype: str | None = None,
    canonical_facts: dict[str, Any] | None = None,
    asset_specific_facts: dict[str, Any] | None = None,
    assertions: list[dict[str, Any]] | None = None,
    agent_findings: dict[str, Any] | None = None,
    material_index: dict[str, Any] | None = None,
    metadata_update: dict[str, Any] | None = None,
) -> None:
    # Logic adapted from the legacy worker implementation, adjusted for providers.
    existing = _db_fetch_one(
        """
        SELECT id, metadata_jsonb
        FROM visual_semantic_outputs
        WHERE visual_asset_id = %s::uuid
          AND (%s::uuid IS NULL OR run_id = %s::uuid)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (visual_asset_id, run_id, run_id),
    )
    if existing and existing.get("id"):
        metadata = existing.get("metadata_jsonb") if isinstance(existing.get("metadata_jsonb"), dict) else {}
        if metadata_update:
            metadata.update(metadata_update)
        _db_execute(
            """
            UPDATE visual_semantic_outputs
            SET output_kind = COALESCE(%s, output_kind),
                asset_type = COALESCE(%s, asset_type),
                asset_subtype = COALESCE(%s, asset_subtype),
                canonical_facts_jsonb = COALESCE(%s::jsonb, canonical_facts_jsonb),
                asset_specific_facts_jsonb = COALESCE(%s::jsonb, asset_specific_facts_jsonb),
                assertions_jsonb = COALESCE(%s::jsonb, assertions_jsonb),
                agent_findings_jsonb = COALESCE(%s::jsonb, agent_findings_jsonb),
                material_index_jsonb = COALESCE(%s::jsonb, material_index_jsonb),
                metadata_jsonb = %s::jsonb,
                tool_run_id = COALESCE(%s::uuid, tool_run_id)
            WHERE id = %s::uuid
            """,
            (
                output_kind,
                asset_type,
                asset_subtype,
                json.dumps(canonical_facts, ensure_ascii=False, default=str) if canonical_facts is not None else None,
                json.dumps(asset_specific_facts, ensure_ascii=False, default=str) if asset_specific_facts is not None else None,
                json.dumps(assertions, ensure_ascii=False, default=str) if assertions is not None else None,
                json.dumps(agent_findings, ensure_ascii=False, default=str) if agent_findings is not None else None,
                json.dumps(material_index, ensure_ascii=False, default=str) if material_index is not None else None,
                json.dumps(metadata, ensure_ascii=False, default=str),
                tool_run_id,
                existing["id"],
            ),
        )
        return

    _db_execute(
        """
        INSERT INTO visual_semantic_outputs (
          id, visual_asset_id, run_id, schema_version, output_kind, asset_type, asset_subtype,
          canonical_facts_jsonb, asset_specific_facts_jsonb, assertions_jsonb,
          agent_findings_jsonb, material_index_jsonb, metadata_jsonb, tool_run_id, created_at
        )
        VALUES (
          %s, %s::uuid, %s::uuid, %s, %s, %s, %s,
          %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::uuid, %s
        )
        """,
        (
            str(uuid4()),
            visual_asset_id,
            run_id,
            schema_version,
            output_kind,
            asset_type,
            asset_subtype,
            json.dumps(canonical_facts or {}, ensure_ascii=False, default=str),
            json.dumps(asset_specific_facts or {}, ensure_ascii=False, default=str),
            json.dumps(assertions or [], ensure_ascii=False, default=str),
            json.dumps(agent_findings or {}, ensure_ascii=False, default=str),
            json.dumps(material_index or {}, ensure_ascii=False, default=str),
            json.dumps(metadata_update or {}, ensure_ascii=False, default=str),
            tool_run_id,
            _utc_now(),
        ),
    )


def vlm_enrich_visual_asset(
    asset: dict[str, Any],
    file_bytes: bytes,
    *,
    run_id: str | None = None,
    ingest_batch_id: str | None = None,
) -> tuple[dict[str, Any], str | None, list[str]]:
    """
    High-level reasoning pass for a visual asset.
    """
    prompt = """You are a Senior Planning Officer and Spatial Analyst.
Analyze this visual asset with planner-grade care. Identify what it IS, and what it IMPLIES,
but only from visible cues. Do not invent policy codes, toponyms, or layers unless explicitly
visible or labelled.

Output JSON strictly matching this schema:
{
  "asset_category": "proposals_map|constraints_map|masterplan|technical_diagram|illustrative_render|photo|other",
  "map_scale_declared": "string or null (e.g., '1:1250')",
  "orientation": "north_up|rotated|unknown",
  "detected_layers": [
    {
      "layer_name": "string",
      "layer_type": "constraint|allocation|administrative|context|infrastructure",
      "representation_style": "polygon_fill|hatching|boundary_line|point_symbol",
      "color_hex_guess": "string or null",
      "is_legend_item": true
    }
  ],
  "extracted_toponyms": ["string"],
  "linked_policy_codes": ["string"],
  "legibility_score": 0.0,
  "interpretation_notes": "Concise planner-grade commentary on ambiguity, limitations, or key cues."
}

Rules:
- Use null for map_scale_declared when not explicitly shown.
- Use "unknown" orientation if no north arrow/compass/grid cue is visible.
- Only include linked_policy_codes if the code is visible in the image.
- color_hex_guess must be a best-effort 6-digit hex (e.g. '#AABBCC') or null.
- Keep interpretation_notes short and grounded in visible evidence.
"""
    
    obj, tool_run_id, errs = _run_vlm_prompt(
        prompt_id="visual_rich_enrichment_v1",
        prompt_version=1,
        prompt_name="Planner visual enrichment",
        purpose="High-level visual asset enrichment for planner navigation.",
        system_template=None,
        user_text=prompt,
        image_bytes=file_bytes,
        output_schema="schemas/VisualAssetEnrichment.schema.json",
        run_id=run_id,
        ingest_batch_id=ingest_batch_id
    )

    if errs:
        raise RuntimeError(f"vlm_enrich_visual_asset_failed:{';'.join(errs)}")
    if not isinstance(obj, dict):
        raise RuntimeError("vlm_enrich_visual_asset_failed:empty_response")

    return obj, tool_run_id, errs
    
def _merge_visual_asset_metadata(*, visual_asset_id: str, patch: dict[str, Any]) -> None:
    _db_execute(
        """
        UPDATE visual_assets
        SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
            updated_at = NOW()
        WHERE id = %s::uuid
        """,
        (json.dumps(patch, ensure_ascii=False, default=str), visual_asset_id),
    )


def _update_visual_asset_identity(
    *,
    visual_asset_id: str,
    asset_type: str | None,
    asset_subtype: str | None,
) -> None:
    if not asset_type and not asset_subtype:
        return
    patch: dict[str, Any] = {}
    if asset_type:
        patch["asset_type"] = asset_type
    if asset_subtype:
        patch["asset_subtype"] = asset_subtype
    _db_execute(
        """
        UPDATE visual_assets
        SET asset_type = COALESCE(%s, asset_type),
            metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb,
            updated_at = NOW()
        WHERE id = %s::uuid
        """,
        (asset_type, json.dumps(patch, ensure_ascii=False, default=str), visual_asset_id),
    )


def extract_visual_asset_facts(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
) -> int:
    if not visual_assets:
        return 0

    asset_types = [
        "photo_existing",
        "photomontage",
        "render_cgi",
        "streetscape_montage",
        "location_plan",
        "site_plan_existing",
        "site_plan_proposed",
        "floor_plan",
        "roof_plan",
        "elevation",
        "section",
        "axonometric_or_3d",
        "diagram_access_transport",
        "diagram_landscape_trees",
        "diagram_daylight_sunlight",
        "diagram_heritage_townscape",
        "diagram_flood_drainage",
        "diagram_phasing_construction",
        "design_material_palette",
        "other_diagram",
    ]

    blob_provider = get_blob_store_provider()
    inserted = 0
    
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        blob_path = asset.get("blob_path")
        if not visual_asset_id or not isinstance(blob_path, str):
            continue
            
        try:
            blob_data = blob_provider.get_blob(blob_path, run_id=run_id, ingest_batch_id=ingest_batch_id)
            image_bytes = blob_data["bytes"]
        except Exception:
            continue

        metadata = asset.get("metadata") or {}
        asset_type_hint = metadata.get("asset_type") or "unknown"
        
        prompt = (
            "You are a planning visual parsing instrument. Return ONLY valid JSON.\n"
            "Choose asset_type from: "
            + ", ".join(asset_types)
            + ".\n"
            "Output shape:\n"
            "{\n"
            '  "asset_type": "...",\n'
            '  "asset_subtype": "...|null",\n'
            '  "canonical_visual_facts": {\n'
            '    "depiction": {"depiction_kind": "photo|drawing|map|diagram|render|mixed", "view_kind": "plan|section|elevation|perspective|axonometric|unknown", "composite_indicator": {"likely_composite": true, "confidence": 0.0}},\n'
            '    "orientation": {"north_arrow_present": true, "north_bearing_degrees": 0, "confidence": 0.0},\n'
            '    "scale_signals": {"scale_bar_present": true, "written_scale_present": true, "dimensions_present": true, "known_object_scale_cues": [], "confidence": 0.0},\n'
            '    "boundary_representation": {"site_boundary_present": true, "boundary_style": "redline|blue_line|dashed|unknown", "confidence": 0.0},\n'
            '    "annotations": {"legend_present": true, "key_present": true, "labels_legible": true, "critical_notes_present": true, "confidence": 0.0},\n'
            '    "viewpoint": {"viewpoint_applicable": true, "declared_viewpoint_present": false, "estimated_camera_height_m": null, "estimated_lens_equiv_mm": null, "estimated_view_direction_degrees": null, "confidence": 0.0},\n'
            '    "height_and_levels": {"height_markers_present": true, "level_datums_present": true, "storey_indicators_present": true, "confidence": 0.0}\n'
            "  },\n"
            '  "asset_specific_facts": {...}\n'
            "}\n"
            f"Asset type hint: {asset_type_hint}.\n"
            "Emit only the asset_specific_facts block relevant to the asset_type."
        )

        obj, tool_run_id, errs = _run_vlm_prompt(
            prompt_id="visual_asset_facts_v1",
            prompt_version=1,
            prompt_name="Visual asset facts",
            purpose="Extract canonical and asset-specific facts from a visual asset.",
            system_template=None,
            user_text=prompt,
            image_bytes=image_bytes,
            output_schema="schemas/VisualAssetFacts.schema.json",
            run_id=run_id,
            ingest_batch_id=ingest_batch_id
        )

        if errs:
            raise RuntimeError(f"visual_asset_facts_failed:{visual_asset_id}:{';'.join(errs)}")
        if not isinstance(obj, dict):
            raise RuntimeError(f"visual_asset_facts_failed:{visual_asset_id}:empty_response")

        asset_type = obj.get("asset_type") if isinstance(obj.get("asset_type"), str) else None
        asset_subtype = obj.get("asset_subtype") if isinstance(obj.get("asset_subtype"), str) else None
        canonical_facts = obj.get("canonical_visual_facts") if isinstance(obj.get("canonical_visual_facts"), dict) else {}
        asset_specific = obj.get("asset_specific_facts") if isinstance(obj.get("asset_specific_facts"), dict) else {}

        _upsert_visual_semantic_output(
            visual_asset_id=visual_asset_id,
            run_id=run_id,
            schema_version="1.0",
            output_kind="classification",
            tool_run_id=tool_run_id,
            asset_type=asset_type,
            asset_subtype=asset_subtype,
            canonical_facts=canonical_facts,
            asset_specific_facts=asset_specific,
            metadata_update={"asset_facts_tool_run_id": tool_run_id},
        )
        if asset_type or asset_subtype:
            _update_visual_asset_identity(
                visual_asset_id=visual_asset_id,
                asset_type=asset_type,
                asset_subtype=asset_subtype,
            )
            _merge_visual_asset_metadata(
                visual_asset_id=visual_asset_id,
                patch={
                    "asset_type_vlm": asset_type,
                    "asset_subtype_vlm": asset_subtype,
                    "asset_type_source": "vlm_asset_facts",
                },
            )
            asset_meta = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            asset_meta["asset_type_vlm"] = asset_type
            asset_meta["asset_subtype_vlm"] = asset_subtype
            asset_meta["asset_type_source"] = "vlm_asset_facts"
            asset["metadata"] = asset_meta
            asset["asset_type"] = asset_type
        inserted += 1

    return inserted

def extract_visual_text_snippets(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
) -> int:
    if not visual_assets:
        return 0

    prompt = (
        "You are an OCR assistant for planning visuals. Return ONLY valid JSON with:\n"
        '{ "snippets": [ { "text": "string", "bbox": [x, y, w, h] | null, "confidence": "low|medium|high" } ], '
        '"limitations": [] }\n'
        "Rules:\n"
        "- Extract readable text from the image, including labels, legends, drawing titles, scale notes.\n"
        "- If text is unreadable, return an empty list.\n"
        "- bbox is optional; when unsure, set it to null.\n"
    )

    blob_provider = get_blob_store_provider()
    total = 0
    
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        blob_path = asset.get("blob_path")
        if not visual_asset_id or not isinstance(blob_path, str):
            continue
            
        try:
            blob_data = blob_provider.get_blob(blob_path, run_id=run_id, ingest_batch_id=ingest_batch_id)
            image_bytes = blob_data["bytes"]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"visual_text_snippets_blob_failed:{visual_asset_id}:{exc}") from exc

        obj, tool_run_id, errs = _run_vlm_prompt(
            prompt_id="visual_text_snippets_v1",
            prompt_version=1,
            prompt_name="Visual text extraction",
            purpose="Extract visible text from planning visuals for traceable linkage.",
            system_template=None,
            user_text=prompt,
            image_bytes=image_bytes,
            output_schema="schemas/VisualTextSnippets.schema.json",
            run_id=run_id,
            ingest_batch_id=ingest_batch_id
        )
        
        if errs:
            raise RuntimeError(f"visual_text_snippets_failed:{visual_asset_id}:{';'.join(errs)}")
        if not isinstance(obj, dict):
            raise RuntimeError(f"visual_text_snippets_failed:{visual_asset_id}:empty_response")
        snippets = obj.get("snippets")
        if not isinstance(snippets, list):
            continue

        snippet_count = 0
        for idx, snippet in enumerate(snippets, start=1):
            if not isinstance(snippet, dict):
                continue
            text = snippet.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            bbox = snippet.get("bbox")
            if isinstance(bbox, list) and len(bbox) == 4:
                try:
                    x0, y0, x1, y1 = [int(float(v)) for v in bbox]
                    if x1 <= x0 or y1 <= y0:
                        x1 = x0 + max(0, x1)
                        y1 = y0 + max(0, y1)
                    bbox = [x0, y0, x1, y1]
                except Exception:
                    bbox = None
            else:
                bbox = None
            bbox_quality = "approx" if bbox else "none"

            evidence_ref = f"visual_text::{visual_asset_id}::snippet-{idx}"
            evidence_ref_id = _ensure_evidence_ref_row(
                evidence_ref,
                run_id=run_id,
                document_id=asset.get("document_id"),
                locator_type="visual_asset",
                locator_value=str(visual_asset_id),
                excerpt=text.strip(),
            )
            _db_execute(
                """
                INSERT INTO visual_asset_regions (
                  id, visual_asset_id, run_id, region_type, bbox, bbox_quality,
                  mask_id, caption_text, evidence_ref_id, metadata_jsonb, created_at
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s::uuid, %s, %s::uuid, %s::jsonb, %s)
                """,
                (
                    str(uuid4()),
                    visual_asset_id,
                    run_id,
                    "text_snippet",
                    json.dumps(bbox, ensure_ascii=False, default=str) if bbox else None,
                    bbox_quality,
                    None,
                    text.strip(),
                    evidence_ref_id,
                    json.dumps(
                        {
                            "confidence": snippet.get("confidence"),
                            "source": "vlm_text",
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                    _utc_now(),
                ),
            )
            snippet_count += 1

        if snippet_count > 0:
            _upsert_visual_semantic_output(
                visual_asset_id=visual_asset_id,
                run_id=run_id,
                schema_version="1.0",
                output_kind="classification",
                tool_run_id=tool_run_id,
                metadata_update={"text_snippet_count": snippet_count},
            )
            total += snippet_count

    return total

def _build_material_index(assertions: list[dict[str, Any]]) -> dict[str, Any]:
    index: dict[str, dict[str, Any]] = {}
    for assertion in assertions:
        tags = assertion.get("material_consideration_tags") if isinstance(assertion, dict) else None
        assertion_id = assertion.get("assertion_id") if isinstance(assertion, dict) else None
        if not isinstance(tags, list) or not assertion_id:
            continue
        for tag in tags:
            if not isinstance(tag, str):
                continue
            entry = index.setdefault(tag, {"assertion_ids": [], "agent_mentions": []})
            entry["assertion_ids"].append(assertion_id)
    return index


def extract_visual_region_assertions(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
) -> int:
    if not visual_assets:
        return 0

    prompt_id = "visual_region_assertions_v1"
    total_assertions = 0
    blob_provider = get_blob_store_provider()

    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        if not visual_asset_id:
            continue
        semantic_row = _db_fetch_one(
            """
            SELECT canonical_facts_jsonb, asset_specific_facts_jsonb, asset_type, asset_subtype, metadata_jsonb
            FROM visual_semantic_outputs
            WHERE visual_asset_id = %s::uuid
              AND (%s::uuid IS NULL OR run_id = %s::uuid)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (visual_asset_id, run_id, run_id),
        )
        canonical_facts = semantic_row.get("canonical_facts_jsonb") if isinstance(semantic_row, dict) else {}
        asset_specific = semantic_row.get("asset_specific_facts_jsonb") if isinstance(semantic_row, dict) else {}
        asset_type = semantic_row.get("asset_type") if isinstance(semantic_row, dict) else None
        asset_subtype = semantic_row.get("asset_subtype") if isinstance(semantic_row, dict) else None

        region_rows = _db_fetch_all(
            """
            SELECT id, bbox, bbox_quality, caption_text, metadata_jsonb
            FROM visual_asset_regions
            WHERE visual_asset_id = %s::uuid
              AND (%s::uuid IS NULL OR run_id = %s::uuid)
            ORDER BY created_at
            """,
            (visual_asset_id, run_id, run_id),
        )
        if not region_rows:
            continue

        assertions: list[dict[str, Any]] = []
        for region in region_rows:
            region_id = str(region.get("id"))
            meta = region.get("metadata_jsonb") if isinstance(region.get("metadata_jsonb"), dict) else {}
            region_blob_path = meta.get("region_blob_path")
            region_evidence_ref = meta.get("evidence_ref")
            if not isinstance(region_blob_path, str):
                continue
            try:
                blob_data = blob_provider.get_blob(region_blob_path, run_id=run_id, ingest_batch_id=ingest_batch_id)
                image_bytes = blob_data["bytes"]
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"visual_region_blob_failed:{region_id}:{exc}") from exc

            prompt = (
                "You are a planning visual assertion instrument. Return ONLY valid JSON.\n"
                "Given a cropped region from a planning visual, produce atomic assertions anchored to this region.\n"
                "Do NOT assess policy compliance or planning balance; describe what the region appears to show or claim.\n"
                "Output shape:\n"
                "{\n"
                '  "assertions": [\n'
                "    {\n"
                '      "assertion_id": "uuid",\n'
                '      "assertion_type": "string",\n'
                '      "statement": "string",\n'
                '      "polarity": "supports|raises_risk|neutral",\n'
                '      "basis": ["string"],\n'
                '      "confidence": 0.0,\n'
                '      "risk_flags": ["string"],\n'
                '      "material_consideration_tags": ["string"],\n'
                '      "follow_up_requests": ["string"],\n'
                f'      "evidence_region_id": "{region_id}"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "Use assertion_type from this vocabulary when possible:\n"
                "design_scale_massing, design_form_roofline, design_materiality, design_frontage_and_activation,\n"
                "design_rhythm_grain, townscape_subordination_or_dominance, townscape_skyline_effect,\n"
                "townscape_view_corridor_effect, townscape_street_enclosure, heritage_setting_effect,\n"
                "heritage_harm_signal, heritage_view_of_designated_asset, amenity_overlooking_signal,\n"
                "amenity_enclosure_outlook_signal, amenity_daylight_sunlight_signal, amenity_noise_activity_signal,\n"
                "access_point_and_visibility_signal, servicing_feasibility_signal, parking_cycle_provision_signal,\n"
                "trees_retention_or_loss_signal, landscape_character_signal, drainage_strategy_signal, flood_risk_signal,\n"
                "context_omission_risk, scale_presentation_risk, idealisation_risk, viewpoint_bias_risk.\n"
                "Material consideration tags should be chosen from:\n"
                "design.scale_massing, design.form_roofline, design.materials_detailing, design.public_realm_frontage,\n"
                "townscape.character_appearance, townscape.views_skyline, townscape.street_enclosure,\n"
                "heritage.setting_significance, heritage.views_assets,\n"
                "amenity.privacy_overlooking, amenity.daylight_sunlight, amenity.outlook_enclosure,\n"
                "transport.access_highway_safety, transport.parking_cycle, transport.servicing,\n"
                "landscape.trees_planting, landscape.open_space, ecology.habitat_cues,\n"
                "water.flood_risk, water.drainage_suds, construction.phasing_logistics,\n"
                "evidence.representation_limits.\n"
                f"Asset type: {asset_type or 'unknown'}; asset subtype: {asset_subtype or 'null'}.\n"
                f"Canonical facts: {json.dumps(canonical_facts, ensure_ascii=False, default=str)}\n"
                f"Asset-specific facts: {json.dumps(asset_specific, ensure_ascii=False, default=str)}\n"
                f"Region bbox: {json.dumps(region.get('bbox'), ensure_ascii=False, default=str)}\n"
                f"Region caption: {region.get('caption_text') or ''}\n"
            )

            obj, tool_run_id, errs = _run_vlm_prompt(
                prompt_id=prompt_id,
                prompt_version=1,
                prompt_name="Region assertions",
                purpose="Extract region-level assertions from a visual crop.",
                system_template=None,
                user_text=prompt,
                image_bytes=image_bytes,
                output_schema="schemas/VisualRegionAssertions.schema.json",
                run_id=run_id,
                ingest_batch_id=ingest_batch_id,
            )
            if errs:
                raise RuntimeError(f"visual_region_assertions_failed:{region_id}:{';'.join(errs)}")
            if not isinstance(obj, dict):
                raise RuntimeError(f"visual_region_assertions_failed:{region_id}:empty_response")
            region_assertions = obj.get("assertions") if isinstance(obj.get("assertions"), list) else []
            for assertion in region_assertions:
                if not isinstance(assertion, dict):
                    continue
                assertion_id = assertion.get("assertion_id")
                try:
                    if not isinstance(assertion_id, str):
                        raise ValueError("invalid")
                    UUID(assertion_id)
                except Exception:  # noqa: BLE001
                    assertion_id = str(uuid4())
                assertion["assertion_id"] = assertion_id
                if not assertion.get("evidence_region_id"):
                    assertion["evidence_region_id"] = region_id
                if isinstance(region_evidence_ref, str) and region_evidence_ref:
                    assertion["evidence_region_ref"] = region_evidence_ref
                assertions.append(assertion)
            total_assertions += len(region_assertions)

        material_index = _build_material_index(assertions)
        _upsert_visual_semantic_output(
            visual_asset_id=visual_asset_id,
            run_id=run_id,
            schema_version="1.0",
            output_kind="classification",
            tool_run_id=None,
            assertions=assertions,
            material_index=material_index,
            metadata_update={"region_assertions_count": len(assertions)},
        )

    return total_assertions
def extract_visual_agent_findings(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_assets: list[dict[str, Any]],
) -> int:
    if not visual_assets:
        return 0

    system_template = (
        "You are a planning specialist review panel. Return ONLY valid JSON with the shape:\n"
        "{\n"
        '  "agent_findings": {\n'
        '    "Design & Character Agent": {\n'
        '      "agent_name": "Design & Character Agent",\n'
        '      "scope_tags": ["design.scale_massing", "design.form_roofline", "design.materials_detailing", "design.public_realm_frontage"],\n'
        '      "supported_assertions": [{"assertion_id": "uuid", "commentary": "string", "confidence_adjustment": -0.2}],\n'
        '      "challenged_assertions": [{"assertion_id": "uuid", "commentary": "string", "confidence_adjustment": -0.2, "additional_risk_flags": ["string"]}],\n'
        '      "additional_assertions": [ {"assertion_id": "uuid", "assertion_type": "string", "statement": "string", "polarity": "supports|raises_risk|neutral", "basis": ["string"], "confidence": 0.0, "risk_flags": ["string"], "material_consideration_tags": ["string"], "follow_up_requests": ["string"]} ],\n'
        '      "notable_omissions": ["string"]\n'
        "    },\n"
        '    "Townscape & Visual Impact Agent": { ... },\n'
        '    "Heritage & Setting Agent": { ... },\n'
        '    "Residential Amenity Agent": { ... },\n'
        '    "Access, Parking & Servicing Agent": { ... },\n'
        '    "Landscape & Trees Agent": { ... },\n'
        '    "Water, Flood & Drainage Agent": { ... },\n'
        '    "Representation Integrity Agent": { ... }\n'
        "  }\n"
        "}\n"
        "Rules:\n"
        "- Only reference assertion_id values that exist in the provided assertions list.\n"
        "- If there is nothing to add, return empty arrays and empty omissions.\n"
        "- Keep commentary concise and in officer-report language.\n"
        "- Do not decide compliance or planning balance; focus on evidence quality and visual signals.\n"
    )

    updated = 0
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        if not visual_asset_id:
            continue
        semantic_row = _db_fetch_one(
            """
            SELECT canonical_facts_jsonb, asset_specific_facts_jsonb, asset_type, asset_subtype, assertions_jsonb
            FROM visual_semantic_outputs
            WHERE visual_asset_id = %s::uuid
              AND (%s::uuid IS NULL OR run_id = %s::uuid)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (visual_asset_id, run_id, run_id),
        )
        if not isinstance(semantic_row, dict):
            continue
        assertions = semantic_row.get("assertions_jsonb") if isinstance(semantic_row.get("assertions_jsonb"), list) else []
        if not assertions:
            continue
        canonical_facts = semantic_row.get("canonical_facts_jsonb") if isinstance(semantic_row.get("canonical_facts_jsonb"), dict) else {}
        asset_specific = semantic_row.get("asset_specific_facts_jsonb") if isinstance(semantic_row.get("asset_specific_facts_jsonb"), dict) else {}
        asset_type = semantic_row.get("asset_type") if isinstance(semantic_row.get("asset_type"), str) else None
        asset_subtype = semantic_row.get("asset_subtype") if isinstance(semantic_row.get("asset_subtype"), str) else None

        obj, tool_run_id, errs = run_llm_prompt(
            prompt_id="visual_agent_findings_v1",
            prompt_version=1,
            prompt_name="Visual agent findings",
            purpose="Review visual assertions with specialist planning lenses.",
            system_template=system_template,
            user_payload={
                "asset_type": asset_type,
                "asset_subtype": asset_subtype,
                "canonical_facts": canonical_facts,
                "asset_specific_facts": asset_specific,
                "assertions": assertions,
            },
            output_schema=None,
            ingest_batch_id=ingest_batch_id,
            run_id=run_id,
        )

        if errs:
            raise RuntimeError(f"visual_agent_findings_failed:{visual_asset_id}:{';'.join(errs)}")
        if not isinstance(obj, dict) or not isinstance(obj.get("agent_findings"), dict):
            raise RuntimeError(f"visual_agent_findings_failed:{visual_asset_id}:empty_response")
        agent_findings = obj.get("agent_findings") or {}
        if isinstance(agent_findings, dict):
            for agent in agent_findings.values():
                if not isinstance(agent, dict):
                    continue
                additional = agent.get("additional_assertions")
                if isinstance(additional, list):
                    for extra in additional:
                        if not isinstance(extra, dict):
                            continue
                        assertion_id = extra.get("assertion_id")
                        try:
                            if not isinstance(assertion_id, str):
                                raise ValueError("invalid")
                            UUID(assertion_id)
                        except Exception:
                            assertion_id = str(uuid4())
                        extra["assertion_id"] = assertion_id

        _upsert_visual_semantic_output(
            visual_asset_id=visual_asset_id,
            run_id=run_id,
            schema_version="1.0",
            output_kind="classification",
            tool_run_id=tool_run_id,
            agent_findings=agent_findings,
            metadata_update={"agent_findings_tool_run_id": tool_run_id},
        )
        updated += 1

    return updated


def _load_redline_mask_base64(
    *,
    visual_asset_id: str,
    run_id: str | None,
) -> tuple[str | None, str | None]:
    row = _db_fetch_one(
        """
        SELECT id, mask_artifact_path
        FROM segmentation_masks
        WHERE visual_asset_id = %s::uuid
          AND label = 'red_line_boundary'
          AND (%s::uuid IS NULL OR run_id = %s::uuid)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (visual_asset_id, run_id, run_id),
    )
    if not isinstance(row, dict):
        return None, None
    mask_path = row.get("mask_artifact_path")
    if not isinstance(mask_path, str):
        return None, None
        
    blob_provider = get_blob_store_provider()
    try:
        blob_data = blob_provider.get_blob(mask_path) # No run_id needed for read?
        mask_bytes = blob_data["bytes"]
        if not mask_bytes:
            return None, None
        return base64.b64encode(mask_bytes).decode("ascii"), row.get("id")
    except Exception:
        return None, None


def detect_redline_boundary_mask(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    visual_asset_id: str,
    blob_path: str,
) -> tuple[str | None, str | None]:
    # Need to check if configured? Providers handle config checks.
    
    blob_provider = get_blob_store_provider()
    try:
        blob_data = blob_provider.get_blob(blob_path, run_id=run_id, ingest_batch_id=ingest_batch_id)
        image_bytes = blob_data["bytes"]
    except Exception:
        return None, None

    prompt = (
        "You are identifying red line boundaries on planning maps and site plans.\n"
        "Return ONLY JSON with:\n"
        '{ "red_line_present": true|false, "bbox": [x0, y0, x1, y1] | null, '
        '"confidence": "low|medium|high", "notes": [] }\n'
        "Rules:\n"
        "- bbox must tightly bound the red line boundary if present.\n"
        "- If no red line boundary is visible, set red_line_present=false and bbox=null.\n"
    )
    
    obj, tool_run_id, errs = _run_vlm_prompt(
        prompt_id="visual_redline_bbox_v1",
        prompt_version=1,
        prompt_name="Red line boundary detector",
        purpose="Detect a red line boundary region for georeferencing.",
        system_template=None,
        user_text=prompt,
        image_bytes=image_bytes,
        output_schema="schemas/VisualRedlineDetection.schema.json",
        run_id=run_id,
        ingest_batch_id=ingest_batch_id
    )
    
    if errs or not isinstance(obj, dict):
        return None, None
    if obj.get("red_line_present") is not True:
        return None, None
    bbox = obj.get("bbox")
    if not (isinstance(bbox, list) and len(bbox) == 4):
        return None, None
    try:
        x0, y0, x1, y1 = [int(float(v)) for v in bbox]
        if x1 <= x0 or y1 <= y0:
            return None, None
        bbox = [x0, y0, x1, y1]
    except Exception:
        return None, None

    # Now use SegmentationProvider to get the exact mask from the bbox
    seg_provider = get_segmentation_provider()
    try:
        # Prompt SAM2 with the bbox
        seg_result = seg_provider.segment(
            image=image_bytes,
            prompts=[{"type": "box", "data": bbox}], # Check provider input format! 
            # My provider implementation expects prompts list.
            # apps/api/tpa_api/providers/segmentation_http.py expects 'prompts': prompts
            # The HTTP service usually takes a list of prompts.
            # I need to verify what the underlying service expects.
            # Legacy payload shape: {"image_base64": ..., "prompts": {"box": bbox}}
            # My provider: `payload = { "image_base64": ..., "prompts": prompts }`
            # So I should pass `{"box": bbox}` as the prompts object if that's what the service wants?
            # Wait, `SegmentationProvider` says `prompts: list[dict]`.
            # `HttpSegmentationProvider` passes it as `prompts`.
            # If the backend expects `{"box": ...}` dict, I should probably adapt or pass dict.
            # Let's assume for now I pass `{"box": bbox}` as the prompts argument, even if type hint says list.
            # Legacy payload shape used prompts={"box": bbox}.
            # So `prompts` is a dict there. My interface said list.
            # I will pass the dict for now to match the backend expectation.
            options={"run_id": run_id, "ingest_batch_id": ingest_batch_id}
        )
    except Exception:
        return None, None

    # Need to hack the provider call slightly if type mismatch.
    # I'll update the provider usage here to pass the dict if the service needs it.
    # Re-reading `segmentation_http.py`:
    # payload = { "image_base64": ..., "prompts": prompts }
    # So if I pass prompts={"box": bbox}, it sends `{"prompts": {"box": bbox}}`. Correct.
    
    # Legacy worker passed prompts={"box": bbox}.
    # So I call `seg_provider.segment(..., prompts={"box": bbox})`.
    
    # But wait, `segment` signature is `prompts: list[dict] | None`. 
    # I should update the signature or ignore type checking here.
    # Ideally, the provider should normalize.
    # I will pass `{"box": bbox}` and ignore type hint for now.
    
    prompts_payload = {"box": bbox} # type: ignore
    try:
        seg_result = seg_provider.segment(
            image=image_bytes,
            prompts=prompts_payload, 
            options={"run_id": run_id, "ingest_batch_id": ingest_batch_id}
        )
    except Exception:
        return None, None

    masks = seg_result.get("masks")
    if not masks:
        return None, None
        
    mask = masks[0]
    mask_b64 = mask.get("mask_png_base64")
    if not mask_b64:
        return None, None
        
    # Decoding base64 function is local to this file, but need imports?
    # I have _decode_base64_payload helper? No, I need to copy it or import it.
    # It is in `segmentation.py`. I'll duplicate `_decode_base64_payload` and `_mask_png_to_rle` 
    # or better, import them.
    from tpa_api.ingestion.segmentation import _decode_base64_payload, _mask_png_to_rle
    
    mask_bytes = _decode_base64_payload(mask_b64)
    mask_rle = _mask_png_to_rle(mask_bytes)
    if not mask_rle:
        return None, None
        
    prefix = f"derived/visual_masks/{visual_asset_id}"
    mask_blob_path = f"{prefix}/redline-mask-{uuid4()}.png"
    
    blob_provider.put_blob(
        mask_blob_path, 
        mask_bytes, 
        content_type="image/png",
        run_id=run_id,
        ingest_batch_id=ingest_batch_id
    )
    
    mask_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO segmentation_masks (
          id, visual_asset_id, run_id, label, prompt, mask_artifact_path, mask_rle_jsonb,
          bbox, bbox_quality, confidence, tool_run_id, created_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s::uuid, %s)
        """,
        (
            mask_id,
            visual_asset_id,
            run_id,
            "red_line_boundary",
            "bbox_prompt",
            mask_blob_path,
            json.dumps(mask_rle, ensure_ascii=False, default=str),
            json.dumps(bbox, ensure_ascii=False, default=str),
            "exact",
            mask.get("confidence"),
            tool_run_id,
            _utc_now(),
        ),
    )
    
    # Also create visual region? Yes
    region_id = str(uuid4())
    evidence_ref = f"visual_redline::{visual_asset_id}::{region_id}"
    evidence_ref_id = _ensure_evidence_ref_row(evidence_ref, run_id=run_id)
    
    _db_execute(
        """
        INSERT INTO visual_asset_regions (
          id, visual_asset_id, run_id, region_type, bbox, bbox_quality,
          mask_id, caption_text, evidence_ref_id, metadata_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s::uuid, %s::jsonb, %s)
        """,
        (
            region_id,
            visual_asset_id,
            run_id,
            "red_line_boundary",
            json.dumps(bbox, ensure_ascii=False, default=str),
            "exact",
            mask_id,
            None,
            evidence_ref_id,
            json.dumps(
                {
                    "source": "sam2_prompt",
                    "confidence": mask.get("confidence"),
                    "tool_run_id": tool_run_id,
                },
                ensure_ascii=False,
                default=str,
            ),
            _utc_now(),
        ),
    )
    
    return mask_b64, mask_id
