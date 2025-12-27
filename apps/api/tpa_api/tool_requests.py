from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException

from .blob_store import read_blob_bytes, to_data_url, write_blob_bytes
from .chart_renderer import render_chart_svg
from .db import _db_execute, _db_fetch_all, _db_fetch_one
from .evidence import _parse_evidence_ref
from .model_clients import _ensure_model_role_sync, _vlm_model_id
from .spatial_fingerprint import compute_site_fingerprint_sync
from .text_utils import _extract_json_object
from .time_utils import _utc_now


def _uuid_or_400(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(value))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{field_name} must be a UUID") from exc


def persist_tool_requests_for_move(
    *,
    run_id: str,
    move_event_id: str | None,
    tool_requests: list[dict[str, Any]],
) -> list[str]:
    """
    Best-effort persistence for Move 3+ ToolRequests so they are executable (not just logged in JSON).

    Returns list of persisted tool_request_ids.
    """
    now = _utc_now()
    persisted: list[str] = []
    for tr in tool_requests[:200]:
        if not isinstance(tr, dict):
            continue
        tool_request_id = tr.get("tool_request_id")
        if not isinstance(tool_request_id, str):
            tool_request_id = str(uuid4())
        try:
            tool_request_id = _uuid_or_400(tool_request_id, field_name="tool_request_id")
        except HTTPException:
            tool_request_id = str(uuid4())

        tool_name = tr.get("tool_name") if isinstance(tr.get("tool_name"), str) and tr.get("tool_name") else "request_instrument"
        instrument_id = tr.get("instrument_id") if isinstance(tr.get("instrument_id"), str) and tr.get("instrument_id") else None
        purpose = tr.get("purpose") if isinstance(tr.get("purpose"), str) else ""
        inputs = tr.get("inputs") if isinstance(tr.get("inputs"), dict) else {}
        blocking = bool(tr.get("blocking")) if tr.get("blocking") is not None else True
        requested_by_move_type = tr.get("requested_by_move_type") if isinstance(tr.get("requested_by_move_type"), str) else None

        try:
            _db_execute(
                """
                INSERT INTO tool_requests (
                  id, run_id, move_event_id, requested_by_move_type, tool_name, instrument_id, purpose,
                  inputs_jsonb, blocking, status, created_at, started_at, completed_at, tool_run_id,
                  outputs_jsonb, evidence_refs_jsonb, error_text
                )
                VALUES (
                  %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s,
                  %s::jsonb, %s, 'pending', %s, NULL, NULL, NULL,
                  '{}'::jsonb, '[]'::jsonb, NULL
                )
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    tool_request_id,
                    run_id,
                    move_event_id,
                    requested_by_move_type,
                    tool_name,
                    instrument_id,
                    purpose,
                    json.dumps(inputs, ensure_ascii=False),
                    blocking,
                    now,
                ),
            )
            persisted.append(tool_request_id)
        except Exception:  # noqa: BLE001
            # Table may not exist yet if the DB volume wasn't reset; do not fail the run.
            continue

    return persisted


def list_tool_requests_for_run(*, run_id: str, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    if status:
        rows = _db_fetch_all(
            """
            SELECT
              id, run_id, move_event_id, requested_by_move_type, tool_name, instrument_id, purpose,
              inputs_jsonb, blocking, status, created_at, started_at, completed_at, tool_run_id,
              outputs_jsonb, evidence_refs_jsonb, error_text
            FROM tool_requests
            WHERE run_id = %s::uuid
              AND status = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (run_id, status, limit),
        )
    else:
        rows = _db_fetch_all(
            """
            SELECT
              id, run_id, move_event_id, requested_by_move_type, tool_name, instrument_id, purpose,
              inputs_jsonb, blocking, status, created_at, started_at, completed_at, tool_run_id,
              outputs_jsonb, evidence_refs_jsonb, error_text
            FROM tool_requests
            WHERE run_id = %s::uuid
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (run_id, limit),
        )

    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "tool_request_id": str(r["id"]),
                "run_id": str(r["run_id"]),
                "move_event_id": str(r["move_event_id"]) if r.get("move_event_id") else None,
                "requested_by_move_type": r.get("requested_by_move_type"),
                "tool_name": r.get("tool_name"),
                "instrument_id": r.get("instrument_id") or "",
                "purpose": r.get("purpose"),
                "inputs": r.get("inputs_jsonb") or {},
                "blocking": bool(r.get("blocking")),
                "status": r.get("status"),
                "created_at": r.get("created_at"),
                "started_at": r.get("started_at"),
                "completed_at": r.get("completed_at"),
                "tool_run_id": str(r["tool_run_id"]) if r.get("tool_run_id") else None,
                "outputs": r.get("outputs_jsonb") or {},
                "evidence_refs": r.get("evidence_refs_jsonb") or [],
                "error_text": r.get("error_text"),
            }
        )
    return out


def get_tool_request(*, tool_request_id: str) -> dict[str, Any] | None:
    tool_request_id = _uuid_or_400(tool_request_id, field_name="tool_request_id")
    r = _db_fetch_one(
        """
        SELECT
          id, run_id, move_event_id, requested_by_move_type, tool_name, instrument_id, purpose,
          inputs_jsonb, blocking, status, created_at, started_at, completed_at, tool_run_id,
          outputs_jsonb, evidence_refs_jsonb, error_text
        FROM tool_requests
        WHERE id = %s::uuid
        """,
        (tool_request_id,),
    )
    if not r:
        return None
    return {
        "tool_request_id": str(r["id"]),
        "run_id": str(r["run_id"]),
        "move_event_id": str(r["move_event_id"]) if r.get("move_event_id") else None,
        "requested_by_move_type": r.get("requested_by_move_type"),
        "tool_name": r.get("tool_name"),
        "instrument_id": r.get("instrument_id") or "",
        "purpose": r.get("purpose"),
        "inputs": r.get("inputs_jsonb") or {},
        "blocking": bool(r.get("blocking")),
        "status": r.get("status"),
        "created_at": r.get("created_at"),
        "started_at": r.get("started_at"),
        "completed_at": r.get("completed_at"),
        "tool_run_id": str(r["tool_run_id"]) if r.get("tool_run_id") else None,
        "outputs": r.get("outputs_jsonb") or {},
        "evidence_refs": r.get("evidence_refs_jsonb") or [],
        "error_text": r.get("error_text"),
    }


def _update_tool_request(
    *,
    tool_request_id: str,
    status: str,
    started_at: Any | None = None,
    completed_at: Any | None = None,
    tool_run_id: str | None = None,
    outputs: dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
    error_text: str | None = None,
) -> None:
    _db_execute(
        """
        UPDATE tool_requests
        SET status = %s,
            started_at = COALESCE(%s, started_at),
            completed_at = COALESCE(%s, completed_at),
            tool_run_id = COALESCE(%s::uuid, tool_run_id),
            outputs_jsonb = COALESCE(%s::jsonb, outputs_jsonb),
            evidence_refs_jsonb = COALESCE(%s::jsonb, evidence_refs_jsonb),
            error_text = %s
        WHERE id = %s::uuid
        """,
        (
            status,
            started_at,
            completed_at,
            tool_run_id,
            json.dumps(outputs, ensure_ascii=False) if outputs is not None else None,
            json.dumps(evidence_refs, ensure_ascii=False) if evidence_refs is not None else None,
            error_text,
            tool_request_id,
        ),
    )


def _run_townscape_vlm_assessment_sync(
    *,
    run_id: str,
    visual_asset_refs: list[str],
    viewpoint_context: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    base_url = _ensure_model_role_sync(role="vlm", timeout_seconds=240.0) or os.environ.get("TPA_VLM_BASE_URL")
    if not base_url:
        return None, None, ["vlm_unconfigured"]

    model_id = os.environ.get("TPA_VLM_MODEL_ID") or _vlm_model_id()
    timeout = None
    url = base_url.rstrip("/") + "/chat/completions"

    # Assemble image parts.
    image_parts: list[dict[str, Any]] = []
    used_refs: list[str] = []
    errors: list[str] = []
    for ref in visual_asset_refs:
        parsed = _parse_evidence_ref(ref) if isinstance(ref, str) else None
        if not parsed:
            continue
        source_type, source_id, fragment_id = parsed
        if source_type != "visual_asset" or fragment_id not in ("blob", "image"):
            continue
        row = _db_fetch_one("SELECT blob_path FROM visual_assets WHERE id = %s::uuid", (source_id,))
        if not row or not row.get("blob_path"):
            errors.append(f"visual_asset_not_found:{source_id}")
            continue
        data, content_type, err = read_blob_bytes(str(row["blob_path"]))
        if err or not data:
            errors.append(f"blob_load_failed:{source_id}:{err}")
            continue
        used_refs.append(ref)
        image_parts.append({"type": "image_url", "image_url": {"url": to_data_url(data, content_type or "image/png")}})

    system = (
        "You are a townscape/visual impact assessment instrument for The Planner's Assistant.\n"
        "Task: given planning images (plans/elevations/photos/photomontages) and viewpoint context, produce planner-legible signals.\n"
        "Return ONLY valid JSON.\n"
        "Do not claim certainty; include explicit limitations.\n"
        "Output shape:\n"
        "{\n"
        "  \"run_id\": UUID,\n"
        "  \"instrument_id\": \"townscape_vlm_assessment\",\n"
        "  \"inputs_logged\": { ... },\n"
        "  \"output_data\": { ... },\n"
        "  \"limitations_statement\": string,\n"
        "  \"timestamp\": ISO8601\n"
        "}\n"
    )
    user_payload = {
        "run_id": run_id,
        "visual_asset_refs": used_refs,
        "viewpoint_context": viewpoint_context or {},
    }

    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [{"type": "text", "text": json.dumps(user_payload, ensure_ascii=False)}, *image_parts],
            },
        ],
    }

    raw_text: str | None = None
    obj: dict[str, Any] | None = None
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        raw_text = data["choices"][0]["message"]["content"]
        obj = _extract_json_object(raw_text)
        if not obj:
            errors.append("vlm_output_not_json_object")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"vlm_call_failed: {exc}")

    # If we couldn't load any images, fail early even if VLM call returns.
    if not used_refs:
        errors.append("no_visual_assets_loaded")
        return None, None, errors

    tool_run_id = str(uuid4())
    started = _utc_now()
    ended = _utc_now()
    try:
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, NULL, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                tool_run_id,
                "instrument.townscape_vlm_assessment",
                json.dumps(
                    {
                        "instrument_id": "townscape_vlm_assessment",
                        "run_id": run_id,
                        "model_id": model_id,
                        "visual_asset_refs": used_refs,
                        "viewpoint_context": viewpoint_context or {},
                        "errors": errors[:10],
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "ok": obj is not None,
                        "raw_text_preview": (raw_text or "")[:1600],
                        "parsed_json": obj,
                        "errors": errors[:10],
                    },
                    ensure_ascii=False,
                ),
                "success" if obj is not None and not errors else ("partial" if obj is not None else "error"),
                started,
                ended,
                "medium" if obj is not None else "low",
                "VLM instrument output is non-deterministic; rely on stored outputs and limitations for traceability.",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"tool_run_persist_failed:{exc}")

    return obj, tool_run_id, errors


def _run_render_simple_chart_sync(
    *,
    run_id: str,
    figure_spec: dict[str, Any],
    plan_project_id: str | None,
    scenario_id: str | None,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    errors: list[str] = []
    svg = render_chart_svg(figure_spec or {})
    blob_path = f"derived/charts/{uuid4()}.svg"
    stored_path, err = write_blob_bytes(blob_path, svg.encode("utf-8"), "image/svg+xml")
    if err or not stored_path:
        errors.append(err or "chart_store_failed")
        return None, None, errors

    now = _utc_now()
    visual_asset_id = str(uuid4())
    metadata = {
        "origin": "generated",
        "chart_type": figure_spec.get("chart_type"),
        "figure_spec": figure_spec,
        "plan_project_id": plan_project_id,
        "scenario_id": scenario_id,
    }
    try:
        _db_execute(
            """
            INSERT INTO visual_assets (id, document_id, page_number, asset_type, blob_path, metadata, created_at, updated_at)
            VALUES (%s, NULL, NULL, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                visual_asset_id,
                figure_spec.get("chart_type") or "chart",
                stored_path,
                json.dumps(metadata, ensure_ascii=False),
                now,
                now,
            ),
        )
        evidence_ref_id = str(uuid4())
        _db_execute(
            """
            INSERT INTO evidence_refs (id, source_type, source_id, fragment_id)
            VALUES (%s, %s, %s, %s)
            """,
            (evidence_ref_id, "visual_asset", visual_asset_id, "image"),
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"visual_asset_persist_failed:{exc}")

    tool_run_id = str(uuid4())
    try:
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, NULL, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                tool_run_id,
                "render.simple_chart",
                json.dumps({"run_id": run_id, "figure_spec": figure_spec}, ensure_ascii=False),
                json.dumps(
                    {
                        "ok": True,
                        "visual_asset_id": visual_asset_id,
                        "artifact_path": stored_path,
                        "evidence_ref": f"visual_asset::{visual_asset_id}::image",
                    },
                    ensure_ascii=False,
                ),
                "success",
                now,
                now,
                "medium",
                "Chart renderer is deterministic; verify input data provenance.",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"tool_run_persist_failed:{exc}")

    return (
        {
            "visual_asset_id": visual_asset_id,
            "artifact_path": stored_path,
            "evidence_ref": f"visual_asset::{visual_asset_id}::image",
            "figure_spec": figure_spec,
        },
        tool_run_id,
        errors,
    )


def _run_environment_agency_flood_sync(
    *,
    run_id: str,
    site_id: str | None = None,
    polygon_wkt: str | None = None,
    polygon_geojson: dict[str, Any] | None = None,
    authority_id: str | None,
    plan_cycle_id: str | None,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """
    OSS flood instrument (deterministic, local):
    - Uses PostGIS intersection against `spatial_features` rows (expected types include `flood-risk-zone`, `flood-storage-area`).

    This is intentionally not a live EA API client: it reports what is present in the canonical store, with limitations.
    """
    errors: list[str] = []
    now = _utc_now()

    inputs_logged: dict[str, Any] = {"authority_id": authority_id, "plan_cycle_id": plan_cycle_id}
    geom_cte_sql: str | None = None
    geom_params: list[Any] = []

    if isinstance(site_id, str) and site_id:
        inputs_logged["site_id"] = site_id
        site = _db_fetch_one("SELECT 1 FROM sites WHERE id = %s::uuid", (site_id,))
        if not site:
            errors.append("site_not_found")
        else:
            inputs_logged["geometry_source"] = "sites.geometry_polygon"
            geom_cte_sql = "SELECT ST_SetSRID(geometry_polygon, 4326) AS g FROM sites WHERE id = %s::uuid"
            geom_params = [site_id]

    if geom_cte_sql is None and isinstance(polygon_wkt, str) and polygon_wkt.strip():
        inputs_logged["geometry_source"] = "polygon_wkt"
        inputs_logged["polygon_wkt_preview"] = polygon_wkt.strip()[:2000]
        geom_cte_sql = "SELECT ST_SetSRID(ST_GeomFromText(%s), 4326) AS g"
        geom_params = [polygon_wkt]

    if geom_cte_sql is None and isinstance(polygon_geojson, dict) and polygon_geojson:
        inputs_logged["geometry_source"] = "polygon_geojson"
        geom_cte_sql = "SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) AS g"
        geom_params = [json.dumps(polygon_geojson, ensure_ascii=False)]

    if geom_cte_sql is None:
        errors.append("missing_geometry_input")
        tool_run_id = str(uuid4())
        try:
            _db_execute(
                """
                INSERT INTO tool_runs (
                  id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
                )
                VALUES (%s, NULL, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
                """,
                (
                    tool_run_id,
                    "instrument.environment_agency_flood",
                    json.dumps({"instrument_id": "environment_agency_flood", **inputs_logged}, ensure_ascii=False),
                    json.dumps({"ok": False, "errors": errors[:10]}, ensure_ascii=False),
                    "error",
                    now,
                    now,
                    "low",
                    "Missing/invalid geometry input for flood instrument.",
                ),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tool_run_persist_failed:{exc}")
        return None, tool_run_id, errors

    try:
        rows = _db_fetch_all(
            """
            WITH geom AS (
              {geom_cte}
            )
            SELECT
              sf.id AS spatial_feature_id,
              sf.type,
              sf.spatial_scope,
              sf.confidence_hint,
              sf.uncertainty_note,
              sf.properties
            FROM spatial_features sf
            WHERE sf.is_active = true
              AND sf.geometry IS NOT NULL
              AND ST_Intersects(ST_SetSRID(sf.geometry, 4326), (SELECT g FROM geom))
              AND sf.type IN ('flood-risk-zone', 'flood-storage-area')
            ORDER BY sf.type ASC
            LIMIT 200
            """.replace("{geom_cte}", geom_cte_sql),
            tuple(geom_params),
        )
    except Exception as exc:  # noqa: BLE001
        rows = []
        errors.append(f"spatial_query_failed:{exc}")

    counts_by_type: dict[str, int] = {}
    hits: list[dict[str, Any]] = []
    for r in rows:
        ftype = r.get("type") if isinstance(r.get("type"), str) else "unknown"
        counts_by_type[ftype] = counts_by_type.get(ftype, 0) + 1
        props = r.get("properties") if isinstance(r.get("properties"), dict) else {}
        hits.append(
            {
                "spatial_feature_id": str(r.get("spatial_feature_id") or ""),
                "type": ftype,
                "spatial_scope": r.get("spatial_scope"),
                "confidence_hint": r.get("confidence_hint"),
                "uncertainty_note": r.get("uncertainty_note"),
                "properties": props,
            }
        )

    summary = "No flood-related spatial_features intersect this site."
    if counts_by_type:
        summary = "Intersects: " + ", ".join([f"{t} ({n})" for t, n in sorted(counts_by_type.items())])

    obj: dict[str, Any] = {
        "run_id": run_id,
        "instrument_id": "environment_agency_flood",
        "inputs_logged": {"instrument_id": "environment_agency_flood", **inputs_logged},
        "output_data": {
            "summary": summary,
            "counts_by_type": counts_by_type,
            "intersections": hits[:200],
        },
        "limitations_statement": (
            "Deterministic PostGIS intersection against `spatial_features` currently loaded in the canonical DB. "
            "This is not a live Environment Agency API call; if flood datasets are missing or not clipped to the authority, results may be incomplete."
        ),
        "timestamp": now.isoformat() if hasattr(now, "isoformat") else None,
    }

    tool_run_id = str(uuid4())
    started = now
    ended = _utc_now()
    try:
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, NULL, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                tool_run_id,
                "instrument.environment_agency_flood",
                json.dumps({"instrument_id": "environment_agency_flood", **inputs_logged}, ensure_ascii=False),
                json.dumps({"ok": True, "output": obj, "errors": errors[:10]}, ensure_ascii=False),
                "success" if not errors else "partial",
                started,
                ended,
                "medium" if hits else "low",
                "Flood instrument is a deterministic evidence instrument; treat outputs as indicators with layer completeness limitations.",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"tool_run_persist_failed:{exc}")

    return obj, tool_run_id, errors


def _run_dft_connectivity_sync(
    *,
    run_id: str,
    site_id: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    authority_id: str | None,
    plan_cycle_id: str | None,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """
    OSS connectivity instrument (deterministic, local proxy).

    Current implementation uses `spatial_features` of type `transport-access-node` (if loaded) to compute simple,
    explainable connectivity signals (counts within distance bands).

    This is NOT a full reproduction of the DfT Connectivity Metric; it is an evidence instrument that can be
    replaced with an official connector later (same instrument_id, different method/version, logged).
    """
    errors: list[str] = []
    now = _utc_now()

    inputs_logged: dict[str, Any] = {"authority_id": authority_id, "plan_cycle_id": plan_cycle_id}
    point_cte_sql: str | None = None
    point_params: list[Any] = []

    if isinstance(site_id, str) and site_id:
        inputs_logged["site_id"] = site_id
        site = _db_fetch_one("SELECT 1 FROM sites WHERE id = %s::uuid", (site_id,))
        if not site:
            errors.append("site_not_found")
        else:
            inputs_logged["point_source"] = "sites.geometry_polygon.centroid"
            point_cte_sql = "SELECT ST_Centroid(ST_SetSRID(geometry_polygon, 4326))::geography AS g FROM sites WHERE id = %s::uuid"
            point_params = [site_id]

    if point_cte_sql is None and isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        inputs_logged["lat"] = float(lat)
        inputs_logged["lon"] = float(lon)
        inputs_logged["point_source"] = "lat_lon"
        point_cte_sql = "SELECT ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography AS g"
        point_params = [float(lon), float(lat)]

    if point_cte_sql is None:
        errors.append("missing_point_input")
        tool_run_id = str(uuid4())
        try:
            _db_execute(
                """
                INSERT INTO tool_runs (
                  id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
                )
                VALUES (%s, NULL, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
                """,
                (
                    tool_run_id,
                    "instrument.dft_connectivity",
                    json.dumps({"instrument_id": "dft_connectivity", **inputs_logged}, ensure_ascii=False),
                    json.dumps({"ok": False, "errors": errors[:10]}, ensure_ascii=False),
                    "error",
                    now,
                    now,
                    "low",
                    "Missing point input for connectivity instrument.",
                ),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tool_run_persist_failed:{exc}")
        return None, tool_run_id, errors

    # Fast fail if layer not present.
    has_layer = _db_fetch_one(
        "SELECT 1 FROM spatial_features WHERE type = 'transport-access-node' AND is_active = true LIMIT 1",
        None,
    )
    if not has_layer:
        errors.append("transport_access_node_layer_missing")
        tool_run_id = str(uuid4())
        try:
            _db_execute(
                """
                INSERT INTO tool_runs (
                  id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
                )
                VALUES (%s, NULL, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
                """,
                (
                    tool_run_id,
                    "instrument.dft_connectivity",
                    json.dumps({"instrument_id": "dft_connectivity", **inputs_logged}, ensure_ascii=False),
                    json.dumps({"ok": False, "errors": errors[:10]}, ensure_ascii=False),
                    "error",
                    now,
                    now,
                    "low",
                    "Missing required spatial layer: spatial_features(type='transport-access-node'). Load public data before running this instrument.",
                ),
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tool_run_persist_failed:{exc}")
        return None, tool_run_id, errors

    try:
        row = _db_fetch_one(
            """
            WITH point AS (
              {point_cte}
            )
            SELECT
              COUNT(*) FILTER (
                WHERE ST_DWithin(ST_SetSRID(sf.geometry, 4326)::geography, (SELECT g FROM point), 400.0)
              ) AS nodes_within_400m,
              COUNT(*) FILTER (
                WHERE ST_DWithin(ST_SetSRID(sf.geometry, 4326)::geography, (SELECT g FROM point), 800.0)
              ) AS nodes_within_800m,
              COUNT(*) FILTER (
                WHERE ST_DWithin(ST_SetSRID(sf.geometry, 4326)::geography, (SELECT g FROM point), 1600.0)
              ) AS nodes_within_1600m
            FROM spatial_features sf
            WHERE sf.is_active = true
              AND sf.geometry IS NOT NULL
              AND sf.type = 'transport-access-node'
              AND ST_DWithin(ST_SetSRID(sf.geometry, 4326)::geography, (SELECT g FROM point), 1600.0)
            """.replace("{point_cte}", point_cte_sql or "SELECT NULL::geography AS g"),
            tuple(point_params),
        )
    except Exception as exc:  # noqa: BLE001
        row = None
        errors.append(f"connectivity_query_failed:{exc}")

    output_data = {
        "nodes_within_400m": int(row.get("nodes_within_400m") or 0) if isinstance(row, dict) else 0,
        "nodes_within_800m": int(row.get("nodes_within_800m") or 0) if isinstance(row, dict) else 0,
        "nodes_within_1600m": int(row.get("nodes_within_1600m") or 0) if isinstance(row, dict) else 0,
        "method": "transport_access_node_counts",
    }
    summary = (
        f"Transport access nodes within 800m: {output_data['nodes_within_800m']} "
        f"(400m: {output_data['nodes_within_400m']}, 1600m: {output_data['nodes_within_1600m']})."
    )

    obj: dict[str, Any] = {
        "run_id": run_id,
        "instrument_id": "dft_connectivity",
        "inputs_logged": {"instrument_id": "dft_connectivity", **inputs_logged},
        "output_data": {"summary": summary, **output_data},
        "limitations_statement": (
            "Proxy metric based on counts of `transport-access-node` features within distance bands of the site centroid. "
            "This is not an official DfT Connectivity Metric score; treat as a local indicator and verify datasets/coverage."
        ),
        "timestamp": now.isoformat() if hasattr(now, "isoformat") else None,
    }

    tool_run_id = str(uuid4())
    started = now
    ended = _utc_now()
    try:
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, NULL, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                tool_run_id,
                "instrument.dft_connectivity",
                json.dumps({"instrument_id": "dft_connectivity", **inputs_logged, "method": "transport_access_node_counts"}, ensure_ascii=False),
                json.dumps({"ok": True, "output": obj, "errors": errors[:10]}, ensure_ascii=False),
                "success" if not errors else "partial",
                started,
                ended,
                "medium",
                "Connectivity instrument output is a relevance/indicator aid; it does not determine planning acceptability.",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"tool_run_persist_failed:{exc}")

    return obj, tool_run_id, errors


def execute_tool_request_sync(*, tool_request_id: str) -> dict[str, Any]:
    tool_request_id = _uuid_or_400(tool_request_id, field_name="tool_request_id")
    row = _db_fetch_one(
        """
        SELECT id, run_id, tool_name, instrument_id, inputs_jsonb, status
        FROM tool_requests
        WHERE id = %s::uuid
        """,
        (tool_request_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="ToolRequest not found")

    status = row.get("status")
    if status == "running":
        raise HTTPException(status_code=409, detail="ToolRequest is already running")

    run_id = str(row["run_id"])
    tool_name = row.get("tool_name") or ""
    instrument_id = row.get("instrument_id") or ""
    inputs = row.get("inputs_jsonb") if isinstance(row.get("inputs_jsonb"), dict) else {}

    started_at = _utc_now()
    _update_tool_request(tool_request_id=tool_request_id, status="running", started_at=started_at, error_text=None)

    try:
        if tool_name == "get_site_fingerprint":
            site_id = inputs.get("site_id")
            if not isinstance(site_id, str):
                raise HTTPException(status_code=400, detail="ToolRequest.inputs.site_id must be provided for get_site_fingerprint")
            authority_id = inputs.get("authority_id") if isinstance(inputs.get("authority_id"), str) else None
            plan_cycle_id = inputs.get("plan_cycle_id") if isinstance(inputs.get("plan_cycle_id"), str) else None
            token_budget = inputs.get("token_budget")
            token_budget = int(token_budget) if isinstance(token_budget, int) else None
            limit_features = inputs.get("limit_features")
            limit_features = int(limit_features) if isinstance(limit_features, int) else None
            fingerprint, tool_run_id, errs = compute_site_fingerprint_sync(
                db_fetch_one=_db_fetch_one,
                db_fetch_all=_db_fetch_all,
                db_execute=_db_execute,
                utc_now=_utc_now,
                site_id=site_id,
                authority_id=authority_id,
                plan_cycle_id=plan_cycle_id,
                token_budget=token_budget,
                limit_features=limit_features,
            )
            completed_at = _utc_now()
            evidence_refs = [f"tool_run::{tool_run_id}::site_fingerprint"]
            outputs = {"fingerprint": fingerprint or {}, "errors": errs[:10]}
            new_status = "success" if fingerprint and not errs else ("partial" if fingerprint else "error")
            _update_tool_request(
                tool_request_id=tool_request_id,
                status=new_status,
                completed_at=completed_at,
                tool_run_id=tool_run_id,
                outputs=outputs,
                evidence_refs=evidence_refs,
                error_text="; ".join(errs[:3]) if errs else None,
            )
            return get_tool_request(tool_request_id=tool_request_id) or {}

        if tool_name == "request_instrument" and instrument_id == "townscape_vlm_assessment":
            visual_asset_refs = inputs.get("visual_asset_refs")
            if not isinstance(visual_asset_refs, list) or not all(isinstance(x, str) for x in visual_asset_refs):
                raise HTTPException(
                    status_code=400, detail="ToolRequest.inputs.visual_asset_refs must be a list of EvidenceRef strings"
                )
            viewpoint_context = inputs.get("viewpoint_context")
            viewpoint_context = viewpoint_context if isinstance(viewpoint_context, dict) else {}
            obj, tool_run_id, errs = _run_townscape_vlm_assessment_sync(
                run_id=run_id, visual_asset_refs=visual_asset_refs, viewpoint_context=viewpoint_context
            )
            completed_at = _utc_now()
            evidence_refs = [f"tool_run::{tool_run_id}::instrument_output"] if tool_run_id else []
            outputs = obj or {"errors": errs[:10]}
            new_status = "success" if obj and not errs else ("partial" if obj else "error")
            _update_tool_request(
                tool_request_id=tool_request_id,
                status=new_status,
                completed_at=completed_at,
                tool_run_id=tool_run_id,
                outputs=outputs if isinstance(outputs, dict) else {"output": outputs},
                evidence_refs=evidence_refs,
                error_text="; ".join(errs[:3]) if errs else None,
            )
            return get_tool_request(tool_request_id=tool_request_id) or {}

        if tool_name == "request_instrument" and instrument_id == "environment_agency_flood":
            site_id = inputs.get("site_id") if isinstance(inputs.get("site_id"), str) else None
            polygon_wkt = inputs.get("polygon_wkt") if isinstance(inputs.get("polygon_wkt"), str) else None
            polygon_geojson = inputs.get("polygon_geojson") if isinstance(inputs.get("polygon_geojson"), dict) else None
            if not (site_id or polygon_wkt or polygon_geojson):
                raise HTTPException(
                    status_code=400,
                    detail="ToolRequest.inputs must include one of: site_id, polygon_wkt, polygon_geojson for environment_agency_flood",
                )
            authority_id = inputs.get("authority_id") if isinstance(inputs.get("authority_id"), str) else None
            plan_cycle_id = inputs.get("plan_cycle_id") if isinstance(inputs.get("plan_cycle_id"), str) else None
            obj, tool_run_id, errs = _run_environment_agency_flood_sync(
                run_id=run_id,
                site_id=site_id,
                polygon_wkt=polygon_wkt,
                polygon_geojson=polygon_geojson,
                authority_id=authority_id,
                plan_cycle_id=plan_cycle_id,
            )
            completed_at = _utc_now()
            evidence_refs = [f"tool_run::{tool_run_id}::instrument_output"] if tool_run_id else []
            outputs = obj or {"errors": errs[:10]}
            new_status = "success" if obj and not errs else ("partial" if obj else "error")
            _update_tool_request(
                tool_request_id=tool_request_id,
                status=new_status,
                completed_at=completed_at,
                tool_run_id=tool_run_id,
                outputs=outputs if isinstance(outputs, dict) else {"output": outputs},
                evidence_refs=evidence_refs,
                error_text="; ".join(errs[:3]) if errs else None,
            )
            return get_tool_request(tool_request_id=tool_request_id) or {}

        if tool_name == "request_instrument" and instrument_id == "dft_connectivity":
            site_id = inputs.get("site_id") if isinstance(inputs.get("site_id"), str) else None
            lat_raw = inputs.get("lat") if inputs.get("lat") is not None else inputs.get("latitude")
            lon_raw = inputs.get("lon") if inputs.get("lon") is not None else inputs.get("longitude")
            lat: float | None = None
            lon: float | None = None
            if lat_raw is not None and str(lat_raw).strip():
                try:
                    lat = float(lat_raw)
                except Exception:  # noqa: BLE001
                    lat = None
            if lon_raw is not None and str(lon_raw).strip():
                try:
                    lon = float(lon_raw)
                except Exception:  # noqa: BLE001
                    lon = None
            if not site_id and (lat is None or lon is None):
                raise HTTPException(
                    status_code=400,
                    detail="ToolRequest.inputs must include either site_id or (lat/lon) for dft_connectivity",
                )
            authority_id = inputs.get("authority_id") if isinstance(inputs.get("authority_id"), str) else None
            plan_cycle_id = inputs.get("plan_cycle_id") if isinstance(inputs.get("plan_cycle_id"), str) else None
            obj, tool_run_id, errs = _run_dft_connectivity_sync(
                run_id=run_id,
                site_id=site_id,
                lat=lat,
                lon=lon,
                authority_id=authority_id,
                plan_cycle_id=plan_cycle_id,
            )
            completed_at = _utc_now()
            evidence_refs = [f"tool_run::{tool_run_id}::instrument_output"] if tool_run_id else []
            outputs = obj or {"errors": errs[:10]}
            new_status = "success" if obj and not errs else ("partial" if obj else "error")
            _update_tool_request(
                tool_request_id=tool_request_id,
                status=new_status,
                completed_at=completed_at,
                tool_run_id=tool_run_id,
                outputs=outputs if isinstance(outputs, dict) else {"output": outputs},
                evidence_refs=evidence_refs,
                error_text="; ".join(errs[:3]) if errs else None,
            )
            return get_tool_request(tool_request_id=tool_request_id) or {}

        if tool_name == "render_figure" or (tool_name == "request_instrument" and instrument_id in ("render_simple_chart", "render_figure")):
            figure_spec = inputs.get("figure_spec") if isinstance(inputs.get("figure_spec"), dict) else None
            if not figure_spec:
                raise HTTPException(status_code=400, detail="ToolRequest.inputs.figure_spec must be provided for render_simple_chart")
            plan_project_id = inputs.get("plan_project_id") if isinstance(inputs.get("plan_project_id"), str) else None
            scenario_id = inputs.get("scenario_id") if isinstance(inputs.get("scenario_id"), str) else None
            obj, tool_run_id, errs = _run_render_simple_chart_sync(
                run_id=run_id,
                figure_spec=figure_spec,
                plan_project_id=plan_project_id,
                scenario_id=scenario_id,
            )
            completed_at = _utc_now()
            evidence_refs = [obj.get("evidence_ref")] if isinstance(obj, dict) and obj.get("evidence_ref") else []
            outputs = obj or {"errors": errs[:10]}
            new_status = "success" if obj and not errs else ("partial" if obj else "error")
            _update_tool_request(
                tool_request_id=tool_request_id,
                status=new_status,
                completed_at=completed_at,
                tool_run_id=tool_run_id,
                outputs=outputs if isinstance(outputs, dict) else {"output": outputs},
                evidence_refs=evidence_refs,
                error_text="; ".join(errs[:3]) if errs else None,
            )
            return get_tool_request(tool_request_id=tool_request_id) or {}

        raise HTTPException(status_code=400, detail=f"Unsupported ToolRequest: tool_name={tool_name} instrument_id={instrument_id}")
    except HTTPException as exc:
        completed_at = _utc_now()
        _update_tool_request(
            tool_request_id=tool_request_id,
            status="error",
            completed_at=completed_at,
            error_text=str(exc.detail),
        )
        raise
    except Exception as exc:  # noqa: BLE001
        completed_at = _utc_now()
        _update_tool_request(
            tool_request_id=tool_request_id,
            status="error",
            completed_at=completed_at,
            error_text=str(exc),
        )
        raise HTTPException(status_code=500, detail="ToolRequest execution failed") from exc
