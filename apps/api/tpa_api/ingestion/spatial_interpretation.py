from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from tpa_api.db import _db_execute, _db_fetch_all
import os

from tpa_api.prompting import _llm_structured_sync
from tpa_api.text_utils import _estimate_tokens
from tpa_api.time_utils import _utc_now


def interpret_spatial_features(
    *,
    authority_id: str,
    token_budget: int | None = None,
    force: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    rows = _db_fetch_all(
        """
        SELECT id, type, spatial_scope, properties
        FROM spatial_features
        WHERE is_active = true
          AND authority_id = %s
        ORDER BY type ASC NULLS LAST, id ASC
        """,
        (authority_id,),
    )
    has_layer_profiles = False
    for row in rows:
        props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
        if props.get("layer_profile") is True:
            has_layer_profiles = True
            break

    candidates: list[dict[str, Any]] = []
    for row in rows:
        feature_id = str(row.get("id") or "")
        if not feature_id:
            continue
        props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
        if has_layer_profiles and props.get("layer_profile") is not True:
            continue
        if not force and isinstance(props.get("interpreted_summary"), str) and props.get("interpreted_summary"):
            continue
        candidates.append(
            {
                "spatial_feature_id": feature_id,
                "feature_type": row.get("type"),
                "spatial_scope": row.get("spatial_scope"),
                "properties": props,
            }
        )

    if not candidates:
        return {"interpreted": 0, "batches": 0, "errors": []}

    budget = int(token_budget) if isinstance(token_budget, int) and token_budget > 0 else 128000
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_tokens = 0
    for feature in candidates:
        est = _estimate_tokens(json.dumps(feature, ensure_ascii=False))
        if current and current_tokens + est > budget:
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(feature)
        current_tokens += est
    if current:
        batches.append(current)

    interpreted = 0
    errors: list[str] = []
    for batch in batches:
        sys = (
            "You are interpreting GIS spatial feature records for planning judgement.\n"
            "Return ONLY valid JSON: {\"interpretations\": [...]}.\n"
            "Each interpretation: {\"spatial_feature_id\": string, \"interpreted_summary\": string, "
            "\"interpreted_constraints\": [string...], \"interpreted_limitations\": string, \"confidence_hint\": string}.\n"
            "Rules:\n"
            "- Use only the provided properties; do not invent facts.\n"
            "- If data is missing or unclear, say so in interpreted_limitations.\n"
            "- Keep summaries planner-legible and neutral.\n"
        )
        payload = {"features": batch}

        temperature = float(os.environ.get("TPA_LLM_SPATIAL_TEMPERATURE", "0.3"))
        obj, tool_run_id, errs = _llm_structured_sync(
            prompt_id="spatial_features.interpretation",
            prompt_version=1,
            prompt_name="Spatial feature interpretation",
            purpose="Interpret spatial feature properties into planner-legible summaries.",
            system_template=sys,
            user_payload=payload,
            output_schema_ref="schemas/SpatialFeatureInterpretation.schema.json",
            run_id=run_id,
            temperature=temperature,
        )
        if errs:
            errors.extend([f"spatial_feature_interpretation:{e}" for e in errs])
        if not isinstance(obj, dict):
            continue
        items = obj.get("interpretations") if isinstance(obj.get("interpretations"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            feature_id = item.get("spatial_feature_id")
            if not isinstance(feature_id, str) or not feature_id:
                continue
            summary = item.get("interpreted_summary")
            if not isinstance(summary, str) or not summary.strip():
                continue
            constraints = item.get("interpreted_constraints") if isinstance(item.get("interpreted_constraints"), list) else []
            limitations = item.get("interpreted_limitations") if isinstance(item.get("interpreted_limitations"), str) else ""
            confidence = item.get("confidence_hint") if isinstance(item.get("confidence_hint"), str) else None

            existing = next((f for f in batch if f.get("spatial_feature_id") == feature_id), None)
            props = existing.get("properties") if isinstance(existing, dict) else {}
            if not isinstance(props, dict):
                props = {}
            props.update(
                {
                    "interpreted_summary": summary.strip(),
                    "interpreted_constraints": [c for c in constraints if isinstance(c, str)],
                    "interpreted_limitations": limitations,
                    "interpreted_confidence_hint": confidence,
                    "interpreted_at": _utc_now().isoformat() if hasattr(_utc_now(), "isoformat") else None,
                    "interpreted_tool_run_id": tool_run_id,
                }
            )

            _db_execute(
                "UPDATE spatial_features SET properties = %s::jsonb WHERE id = %s::uuid",
                (json.dumps(props, ensure_ascii=False), feature_id),
            )
            interpreted += 1

    return {"interpreted": interpreted, "batches": len(batches), "errors": errors[:20]}
