from __future__ import annotations

import json
from uuid import uuid4
from typing import Any

from tpa_api.db import _db_execute, _db_fetch_all
from tpa_api.providers.factory import get_blob_store_provider, get_vectorization_provider
from tpa_api.time_utils import _utc_now


def _bbox_from_geometry(geometry: dict[str, Any] | None) -> list[float] | None:
    if not isinstance(geometry, dict):
        return None
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")
    points: list[tuple[float, float]] = []

    def _collect_ring(ring: Any) -> None:
        if isinstance(ring, list):
            for pt in ring:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    try:
                        points.append((float(pt[0]), float(pt[1])))
                    except Exception:
                        continue

    if geom_type == "Polygon" and isinstance(coords, list):
        for ring in coords:
            _collect_ring(ring)
    elif geom_type == "MultiPolygon" and isinstance(coords, list):
        for poly in coords:
            if isinstance(poly, list):
                for ring in poly:
                    _collect_ring(ring)
    else:
        return None

    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def vectorize_segmentation_masks(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    document_id: str,
    visual_assets: list[dict[str, Any]],
) -> int:
    """
    Vectorizes stored segmentation masks using the VectorizationProvider.
    """
    blob_provider = get_blob_store_provider()
    vec_provider = get_vectorization_provider()

    asset_ids = [a.get("visual_asset_id") for a in visual_assets if a.get("visual_asset_id")]
    if not asset_ids:
        return 0
    
    page_by_asset = {a.get("visual_asset_id"): int(a.get("page_number") or 0) for a in visual_assets}

    mask_rows = _db_fetch_all(
        """
        SELECT id, visual_asset_id, mask_artifact_path, bbox, label
        FROM segmentation_masks
        WHERE visual_asset_id = ANY(%s::uuid[])
          AND (%s::uuid IS NULL OR run_id = %s::uuid)
        ORDER BY created_at
        """,
        (asset_ids, run_id, run_id),
    )
    if not mask_rows:
        return 0

    path_total = 0
    
    for mask in mask_rows:
        mask_id = str(mask.get("id"))
        visual_asset_id = mask.get("visual_asset_id")
        if not visual_asset_id:
            raise RuntimeError(f"vectorization_missing_visual_asset_id:{mask_id}")
            
        mask_path = mask.get("mask_artifact_path")
        if not isinstance(mask_path, str):
            raise RuntimeError(f"vectorization_missing_mask_path:{mask_id}")

        # 1. Get Mask Blob
        try:
            blob_data = blob_provider.get_blob(mask_path, run_id=run_id, ingest_batch_id=ingest_batch_id)
            mask_bytes = blob_data["bytes"]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"vectorization_blob_read_failed:{mask_path}:{exc}") from exc
        if not mask_bytes:
            raise RuntimeError(f"vectorization_blob_empty:{mask_path}")

        # 2. Vectorize
        try:
            result = vec_provider.vectorize(
                image=mask_bytes,
                options={"run_id": run_id, "ingest_batch_id": ingest_batch_id},
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"vectorization_provider_failed:{mask_id}:{exc}") from exc

        if not isinstance(result, dict):
            raise RuntimeError(f"vectorization_invalid_result:{mask_id}")

        features = result.get("features_geojson", {}).get("features", [])
        if not isinstance(features, list):
            raise RuntimeError(f"vectorization_invalid_features:{mask_id}")
        
        # 3. Store Vector Paths
        insert_count = 0
        for idx, feature in enumerate(features, start=1):
            if not isinstance(feature, dict):
                raise RuntimeError(f"vectorization_invalid_feature:{mask_id}:{idx}")
            
            geometry = feature.get("geometry")
            if not geometry:
                raise RuntimeError(f"vectorization_missing_geometry:{mask_id}:{idx}")
                
            bbox = _bbox_from_geometry(geometry) or mask.get("bbox")
            bbox_quality = "exact" if bbox else "none"
            path_id = f"vm-{mask_id}-{idx:03d}"
            
            path_type = feature.get("properties", {}).get("source", "mask_contour")
            
            _db_execute(
                """
                INSERT INTO vector_paths (
                  id, document_id, page_number, ingest_batch_id, source_artifact_id,
                  path_id, path_type, geometry_jsonb, bbox, bbox_quality, metadata_jsonb
                )
                VALUES (%s, %s::uuid, %s, %s::uuid, %s::uuid, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb)
                """,
                (
                    str(uuid4()),
                    document_id,
                    page_by_asset.get(visual_asset_id, 0),
                    ingest_batch_id,
                    None,
                    path_id,
                    path_type,
                    json.dumps(geometry, ensure_ascii=False, default=str),
                    json.dumps(bbox, ensure_ascii=False, default=str) if bbox else None,
                    bbox_quality,
                    json.dumps(
                        {
                            "coord_space": "image_pixels",
                            "vector_source": "segmentation_mask",
                            "visual_asset_id": visual_asset_id,
                            "mask_id": mask_id,
                            "mask_label": mask.get("label"),
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                ),
            )
            insert_count += 1
            
        path_total += insert_count

    return path_total
