from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from tpa_api.db import _db_execute, _db_fetch_one
from tpa_api.time_utils import _utc_now


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _authority_pack_root() -> Path:
    return Path(os.environ.get("TPA_AUTHORITY_PACKS_ROOT", "/authority_packs")).resolve()


def _normalize_key(value: str) -> str:
    lowered = value.strip().lower()
    return _NON_ALNUM.sub("_", lowered).strip("_")


def _iter_coords(value: Any) -> Iterable[tuple[float, float]]:
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return
        if isinstance(value[0], (int, float)) and len(value) >= 2:
            yield (float(value[0]), float(value[1]))
            return
        for item in value:
            yield from _iter_coords(item)


def _geometry_bounds(geometry: dict[str, Any]) -> tuple[float, float, float, float] | None:
    if not isinstance(geometry, dict):
        return None
    geom_type = geometry.get("type")
    if geom_type == "GeometryCollection":
        bounds = None
        for geom in geometry.get("geometries") or []:
            geom_bounds = _geometry_bounds(geom)
            if not geom_bounds:
                continue
            if bounds is None:
                bounds = geom_bounds
            else:
                bounds = (
                    min(bounds[0], geom_bounds[0]),
                    min(bounds[1], geom_bounds[1]),
                    max(bounds[2], geom_bounds[2]),
                    max(bounds[3], geom_bounds[3]),
                )
        return bounds
    coords = geometry.get("coordinates")
    if coords is None:
        return None
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    found = False
    for x, y in _iter_coords(coords):
        found = True
        minx = min(minx, x)
        miny = min(miny, y)
        maxx = max(maxx, x)
        maxy = max(maxy, y)
    if not found:
        return None
    return (minx, miny, maxx, maxy)


def _bbox_polygon(bounds: tuple[float, float, float, float]) -> dict[str, Any]:
    minx, miny, maxx, maxy = bounds
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [minx, miny],
                [maxx, miny],
                [maxx, maxy],
                [minx, maxy],
                [minx, miny],
            ]
        ],
    }


def ingest_authority_gis_layers(
    *,
    authority_id: str,
    plan_cycle_id: str | None = None,
    ingest_batch_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    existing = _db_fetch_one(
        """
        SELECT 1
        FROM spatial_features
        WHERE authority_id = %s
          AND is_active = true
        LIMIT 1
        """,
        (authority_id,),
    )
    if existing and not force:
        return {"inserted_features": 0, "inserted_layers": 0, "skipped": True, "errors": []}

    root = _authority_pack_root() / authority_id
    if not root.exists():
        return {"inserted_features": 0, "inserted_layers": 0, "skipped": True, "errors": ["authority_pack_missing"]}

    gis_layers_path = root / "gis_layers.json"
    layers: list[dict[str, Any]] = []
    if gis_layers_path.exists():
        try:
            layers = json.loads(gis_layers_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            layers = []

    local_dir = root / "gis_data"
    local_files = list(local_dir.glob("*.geojson")) if local_dir.exists() else []
    local_by_key = {_normalize_key(p.stem): p for p in local_files}

    layer_entries: list[dict[str, Any]] = []
    for layer in layers:
        if isinstance(layer, dict) and isinstance(layer.get("name"), str):
            layer_entries.append(layer)

    # Add local-only layers.
    known_keys = {_normalize_key(l.get("name") or "") for l in layer_entries}
    for key, path in local_by_key.items():
        if key in known_keys:
            continue
        layer_entries.append({"name": path.stem, "type": "LocalGeoJSON", "path": str(path)})

    inserted_features = 0
    inserted_layers = 0
    errors: list[str] = []

    for layer in layer_entries:
        layer_name = layer.get("name")
        if not isinstance(layer_name, str):
            continue
        layer_key = _normalize_key(layer_name)
        source_url = layer.get("url") if isinstance(layer.get("url"), str) else None
        source_path = layer.get("path") if isinstance(layer.get("path"), str) else None
        local_path = local_by_key.get(layer_key)
        if source_path and not local_path:
            local_path = Path(source_path)

        features = []
        geometry_types: set[str] = set()
        attribute_keys: set[str] = set()
        bounds: tuple[float, float, float, float] | None = None

        if local_path and local_path.exists():
            try:
                geojson = json.loads(local_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"geojson_parse_failed:{layer_name}:{exc}")
                geojson = {}
            if isinstance(geojson, dict):
                features = geojson.get("features") if isinstance(geojson.get("features"), list) else []

        for idx, feature in enumerate(features):
            if not isinstance(feature, dict):
                continue
            geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else None
            if not geometry:
                continue
            geom_type = geometry.get("type")
            if isinstance(geom_type, str):
                geometry_types.add(geom_type)
            geom_bounds = _geometry_bounds(geometry)
            if geom_bounds:
                bounds = geom_bounds if bounds is None else (
                    min(bounds[0], geom_bounds[0]),
                    min(bounds[1], geom_bounds[1]),
                    max(bounds[2], geom_bounds[2]),
                    max(bounds[3], geom_bounds[3]),
                )
            props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
            for key in props.keys():
                if isinstance(key, str):
                    attribute_keys.add(key)

            properties = {
                **props,
                "layer_name": layer_name,
                "layer_key": layer_key,
                "source_path": str(local_path) if local_path else None,
                "source_url": source_url,
                "feature_index": idx,
            }
            feature_id = str(uuid4())
            try:
                _db_execute(
                    """
                    INSERT INTO spatial_features (
                      id, authority_id, ingest_batch_id, type, spatial_scope,
                      is_active, confidence_hint, uncertainty_note, geometry, properties
                    )
                    VALUES (
                      %s, %s, %s::uuid, %s, %s, true, %s, %s,
                      ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                      %s::jsonb
                    )
                    """,
                    (
                        feature_id,
                        authority_id,
                        ingest_batch_id,
                        layer_key,
                        layer_name,
                        "high" if local_path else "low",
                        None,
                        json.dumps(geometry, ensure_ascii=False),
                        json.dumps(properties, ensure_ascii=False),
                    ),
                )
                inserted_features += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"spatial_insert_failed:{layer_name}:{exc}")

        profile_bounds = bounds or (None if not local_path else None)
        profile_geometry = _bbox_polygon(profile_bounds) if profile_bounds else None
        profile_props = {
            "layer_profile": True,
            "layer_name": layer_name,
            "layer_key": layer_key,
            "feature_count": len(features),
            "geometry_types": sorted(geometry_types),
            "attribute_keys": sorted(attribute_keys),
            "source_url": source_url,
            "source_path": str(local_path) if local_path else None,
            "profile_created_at": _utc_now().isoformat() if hasattr(_utc_now(), "isoformat") else None,
        }
        try:
            _db_execute(
                """
                INSERT INTO spatial_features (
                  id, authority_id, ingest_batch_id, type, spatial_scope,
                  is_active, confidence_hint, uncertainty_note, geometry, properties
                )
                VALUES (
                  %s, %s, %s::uuid, %s, %s, true, %s, %s,
                  %s,
                  %s::jsonb
                )
                """,
                (
                    str(uuid4()),
                    authority_id,
                    ingest_batch_id,
                    f"{layer_key}_profile",
                    layer_name,
                    "medium" if local_path else "low",
                    "Layer profile only; full geometry may be missing." if not local_path else None,
                    json.dumps(profile_geometry, ensure_ascii=False) if profile_geometry else None,
                    json.dumps(profile_props, ensure_ascii=False),
                ),
            )
            inserted_layers += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"layer_profile_insert_failed:{layer_name}:{exc}")

    return {
        "inserted_features": inserted_features,
        "inserted_layers": inserted_layers,
        "skipped": False,
        "errors": errors,
    }
