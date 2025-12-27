from __future__ import annotations

import json
from typing import Any, Callable
from uuid import uuid4


def _is_uuid_str(value: str) -> bool:
    try:
        from uuid import UUID

        UUID(value)
        return True
    except Exception:
        return False


def extract_site_ids_from_state_vector(state_vector: dict[str, Any]) -> list[str]:
    """
    Heuristic extraction of site ids from a ScenarioStateVector.

    This is intentionally permissive while the state vector is still evolving.
    """
    out: list[str] = []

    def add(val: Any) -> None:
        if isinstance(val, str) and _is_uuid_str(val) and val not in out:
            out.append(val)

    add(state_vector.get("site_id"))
    add(state_vector.get("focus_site_id"))

    site_ids = state_vector.get("site_ids")
    if isinstance(site_ids, list):
        for v in site_ids:
            add(v)

    sites = state_vector.get("sites")
    if isinstance(sites, list):
        for s in sites:
            if isinstance(s, dict):
                add(s.get("site_id"))

    return out[:25]


def compute_site_fingerprint_sync(
    *,
    db_fetch_one: Callable[[str, tuple[Any, ...] | list[Any] | None], dict[str, Any] | None],
    db_fetch_all: Callable[[str, tuple[Any, ...] | list[Any] | None], list[dict[str, Any]]],
    db_execute: Callable[[str, tuple[Any, ...] | list[Any] | None], None],
    utc_now: Callable[[], Any],
    site_id: str,
    authority_id: str | None,
    plan_cycle_id: str | None,
    token_budget: int | None = None,
    limit_features: int | None = None,
) -> tuple[dict[str, Any] | None, str, list[str]]:
    """
    Deterministic spatial enrichment tool (Slice C).

    Produces:
    - a ToolRun ("get_site_fingerprint") with logged inputs/outputs + limitations
    - best-effort KG edges (Site -> SpatialFeature INTERSECTS) with tool_run provenance
    - best-effort persistence into site_fingerprints (if table exists)

    Returns (fingerprint_json, tool_run_id, errors).
    """
    tool_run_id = str(uuid4())
    started_at = utc_now()
    errors: list[str] = []
    if isinstance(limit_features, int):
        limit_features = max(1, limit_features)
    if limit_features is None and isinstance(token_budget, int) and token_budget > 0:
        estimated_tokens_per_feature = 200
        limit_features = max(1, token_budget // estimated_tokens_per_feature)

    site = db_fetch_one(
        """
        SELECT
          id,
          ST_AsGeoJSON(geometry_polygon) AS geometry_geojson,
          metadata
        FROM sites
        WHERE id = %s::uuid
        """,
        (site_id,),
    )
    if not site:
        ended_at = utc_now()
        db_execute(
            """
            INSERT INTO tool_runs (id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note)
            VALUES (%s, NULL, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                tool_run_id,
                "get_site_fingerprint",
                json.dumps(
                    {
                        "site_id": site_id,
                        "authority_id": authority_id,
                        "plan_cycle_id": plan_cycle_id,
                        "token_budget": token_budget,
                        "limit_features": limit_features,
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"ok": False, "error": "site_not_found"}, ensure_ascii=False),
                "error",
                started_at,
                ended_at,
                "low",
                "Site not found; cannot compute fingerprint.",
            ),
        )
        return None, tool_run_id, ["site_not_found"]

    where: list[str] = ["sf.is_active = true", "sf.geometry IS NOT NULL", "ST_Intersects(sf.geometry, s.geometry_polygon)"]
    params: list[Any] = []
    if authority_id:
        where.append("(sf.authority_id IS NULL OR sf.authority_id = %s)")
        params.append(authority_id)
    where_sql = " AND ".join(where)

    limit_clause = "LIMIT %s" if isinstance(limit_features, int) else ""
    try:
        rows = db_fetch_all(
            f"""
            SELECT
              sf.id AS spatial_feature_id,
              sf.type,
              sf.spatial_scope,
              sf.confidence_hint,
              sf.uncertainty_note,
              sf.properties
            FROM spatial_features sf
            JOIN sites s ON s.id = %s::uuid
            WHERE {where_sql}
            ORDER BY sf.type ASC
            {limit_clause}
            """,
            tuple([site_id] + params + ([limit_features] if isinstance(limit_features, int) else [])),
        )
    except Exception as exc:  # noqa: BLE001
        rows = []
        errors.append(f"spatial_query_failed: {exc}")

    features: list[dict[str, Any]] = []
    counts_by_type: dict[str, int] = {}
    for r in rows:
        fid = str(r.get("spatial_feature_id") or "")
        ftype = r.get("type") if isinstance(r.get("type"), str) else "unknown"
        counts_by_type[ftype] = counts_by_type.get(ftype, 0) + 1
        props = r.get("properties") if isinstance(r.get("properties"), dict) else {}
        features.append(
            {
                "spatial_feature_id": fid,
                "type": ftype,
                "spatial_scope": r.get("spatial_scope"),
                "confidence_hint": r.get("confidence_hint"),
                "uncertainty_note": r.get("uncertainty_note"),
                "properties": props,
            }
        )

    top_types = sorted(counts_by_type.items(), key=lambda x: (-x[1], x[0]))[:8]
    summary = "No intersecting spatial features found."
    if top_types:
        summary = "Intersects: " + ", ".join([f"{t} ({n})" for t, n in top_types])

    limitations_text = (
        "Deterministic PostGIS intersection checks against spatial_features currently loaded in the canonical DB. "
        "If constraint layers are missing, results will be incomplete. Distances/network connectivity are not yet computed."
    )
    if isinstance(limit_features, int):
        limitations_text = (
            limitations_text
            + f" Intersections were capped at {limit_features} features based on the available token budget."
        )

    fingerprint = {
        "site_id": site_id,
        "authority_id": authority_id,
        "plan_cycle_id": plan_cycle_id,
        "counts_by_type": counts_by_type,
        "intersections": features,
        "summary": summary,
        "limitations_text": limitations_text,
    }

    # Best-effort KG enrichment (Slice C): Site -> SpatialFeature INTERSECTS edges with tool_run provenance.
    try:
        db_execute(
            """
            INSERT INTO kg_node (node_id, node_type, props_jsonb, canonical_fk)
            VALUES (%s::uuid, 'Site', %s::jsonb, %s::uuid)
            ON CONFLICT (node_id) DO NOTHING
            """,
            (site_id, json.dumps({"metadata": site.get("metadata") or {}}, ensure_ascii=False), site_id),
        )

        # Replace prior INTERSECTS edges for this site (we treat KG as the current join fabric).
        db_execute(
            "DELETE FROM kg_edge WHERE src_id = %s::uuid AND edge_type = 'INTERSECTS'",
            (site_id,),
        )

        for f in features[:500]:
            fid = f.get("spatial_feature_id")
            if not isinstance(fid, str) or not _is_uuid_str(fid):
                continue
            db_execute(
                """
                INSERT INTO kg_node (node_id, node_type, props_jsonb, canonical_fk)
                VALUES (%s::uuid, 'SpatialFeature', %s::jsonb, %s::uuid)
                ON CONFLICT (node_id) DO NOTHING
                """,
                (fid, json.dumps({"type": f.get("type"), "spatial_scope": f.get("spatial_scope")}, ensure_ascii=False), fid),
            )
            db_execute(
                """
                INSERT INTO kg_edge (edge_id, src_id, dst_id, edge_type, props_jsonb, evidence_ref_id, tool_run_id)
                VALUES (%s::uuid, %s::uuid, %s::uuid, 'INTERSECTS', %s::jsonb, NULL, %s::uuid)
                """,
                (
                    str(uuid4()),
                    site_id,
                    fid,
                    json.dumps({"relationship": "intersects", "feature_type": f.get("type")}, ensure_ascii=False),
                    tool_run_id,
                ),
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"kg_enrichment_failed: {exc}")

    ended_at = utc_now()
    db_execute(
        """
        INSERT INTO tool_runs (id, ingest_batch_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note)
        VALUES (%s, NULL, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
        """,
        (
            tool_run_id,
            "get_site_fingerprint",
            json.dumps(
                {
                    "site_id": site_id,
                    "authority_id": authority_id,
                    "plan_cycle_id": plan_cycle_id,
                    "token_budget": token_budget,
                    "limit_features": limit_features,
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "ok": True,
                    "counts_by_type": counts_by_type,
                    "intersection_count": len(features),
                    "summary": summary,
                    "errors": errors[:10],
                },
                ensure_ascii=False,
            ),
            "success" if not errors else "partial",
            started_at,
            ended_at,
            "high",
            fingerprint["limitations_text"],
        ),
    )

    # Best-effort persistence into site_fingerprints (if present).
    try:
        previous = db_fetch_one(
            """
            SELECT id
            FROM site_fingerprints
            WHERE site_id = %s::uuid
              AND (
                (%s::uuid IS NULL AND plan_cycle_id IS NULL)
                OR plan_cycle_id = %s::uuid
              )
              AND is_current = true
            LIMIT 1
            """,
            (site_id, plan_cycle_id, plan_cycle_id),
        )
        prev_id = str(previous["id"]) if previous and previous.get("id") else None
        new_id = str(uuid4())
        now = utc_now()
        if prev_id:
            db_execute(
                "UPDATE site_fingerprints SET is_current = false, superseded_by_fingerprint_id = %s::uuid WHERE id = %s::uuid",
                (new_id, prev_id),
            )
        db_execute(
            """
            INSERT INTO site_fingerprints (
              id, site_id, plan_cycle_id, authority_id, fingerprint_jsonb, tool_run_id, created_at, updated_at,
              is_current, superseded_by_fingerprint_id, confidence_hint, uncertainty_note
            )
            VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb, %s::uuid, %s, %s, true, NULL, %s, %s)
            """,
            (
                new_id,
                site_id,
                plan_cycle_id,
                authority_id,
                json.dumps(fingerprint, ensure_ascii=False),
                tool_run_id,
                now,
                now,
                "high",
                fingerprint["limitations_text"],
            ),
        )
    except Exception:
        # Table might not exist yet (stale DB volume), or constraints might block; skip without failing fingerprint itself.
        pass

    return fingerprint, tool_run_id, errors
