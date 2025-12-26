from __future__ import annotations

import base64
import io
import json
from typing import Any
from uuid import uuid4

from PIL import Image

from tpa_api.db import _db_execute
from tpa_api.evidence import _ensure_evidence_ref_row
from tpa_api.providers.factory import get_blob_store_provider, get_segmentation_provider
from tpa_api.time_utils import _utc_now


def _decode_base64_payload(data: str) -> bytes:
    if "base64," in data:
        data = data.split("base64,", 1)[1]
    return base64.b64decode(data)


def _mask_png_to_rle(mask_png_bytes: bytes) -> dict[str, Any] | None:
    try:
        with Image.open(io.BytesIO(mask_png_bytes)) as img:
            if img.mode == "RGBA":
                alpha = img.split()[-1]
                pixels = list(alpha.getdata())
            else:
                img = img.convert("L")
                pixels = list(img.getdata())
            width, height = img.size
    except Exception:
        return None

    counts: list[int] = []
    last = 0
    run_len = 0
    for val in pixels:
        bit = 1 if val > 0 else 0
        if bit != last:
            counts.append(run_len)
            run_len = 0
            last = bit
        run_len += 1
    counts.append(run_len)
    return {"size": [height, width], "counts": counts}


def segment_visual_assets(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    authority_id: str,
    plan_cycle_id: str | None,
    document_id: str,
    visual_assets: list[dict[str, Any]],
) -> tuple[int, int]:
    """
    Orchestrates segmentation using Providers.
    Returns (mask_count, region_count).
    """
    blob_provider = get_blob_store_provider()
    seg_provider = get_segmentation_provider()
    
    prefix = f"docparse/{authority_id}/{plan_cycle_id or 'none'}/{document_id}"

    mask_total = 0
    region_total = 0
    
    for asset in visual_assets:
        visual_asset_id = asset.get("visual_asset_id")
        blob_path = asset.get("blob_path")
        if not visual_asset_id or not isinstance(blob_path, str):
            continue

        # 1. Get Image
        try:
            blob_data = blob_provider.get_blob(blob_path, run_id=run_id, ingest_batch_id=ingest_batch_id)
            image_bytes = blob_data["bytes"]
        except Exception:
            continue # Skip if missing

        # 2. Call Segmentation Provider
        try:
            result = seg_provider.segment(
                image=image_bytes,
                prompts=None, # Auto-segmentation
                options={"run_id": run_id, "ingest_batch_id": ingest_batch_id}
            )
        except Exception:
            continue

        masks = result.get("masks") or []
        caption = (asset.get("metadata") or {}).get("caption")
        
        for idx, mask in enumerate(masks, start=1):
            if not isinstance(mask, dict):
                continue
            
            mask_b64 = mask.get("mask_png_base64")
            if not mask_b64:
                continue
                
            mask_bytes = _decode_base64_payload(mask_b64)
            mask_rle = _mask_png_to_rle(mask_bytes)
            if mask_rle is None:
                continue

            # 3. Store Mask Blob
            mask_blob_path = f"{prefix}/visual_masks/{visual_asset_id}/mask-{idx:03d}.png"
            blob_provider.put_blob(
                mask_blob_path, 
                mask_bytes, 
                content_type="image/png",
                run_id=run_id,
                ingest_batch_id=ingest_batch_id
            )

            # 4. Process BBox
            bbox = mask.get("bbox")
            # Ensure bbox logic matches convention (SAM2 might return [x,y,w,h])
            if isinstance(bbox, list) and len(bbox) == 4:
                x0, y0, x1, y1 = [int(float(v)) for v in bbox]
                # If width/height format detected
                if x1 <= x0 or y1 <= y0:
                    x1 = x0 + max(0, x1)
                    y1 = y0 + max(0, y1)
                bbox = [x0, y0, x1, y1]
            else:
                bbox = None
            
            bbox_quality = "exact" if bbox else "none"
            mask_id = str(uuid4())
            
            _db_execute(
                """
                INSERT INTO segmentation_masks (
                  id, visual_asset_id, run_id, label, prompt, mask_artifact_path, mask_rle_jsonb,
                  bbox, bbox_quality, confidence, created_at
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                """,
                (
                    mask_id,
                    visual_asset_id,
                    run_id,
                    mask.get("label"),
                    mask.get("prompt"),
                    mask_blob_path,
                    json.dumps(mask_rle, ensure_ascii=False),
                    json.dumps(bbox, ensure_ascii=False) if bbox else None,
                    bbox_quality,
                    mask.get("confidence"),
                    _utc_now(),
                ),
            )
            mask_total += 1

            # 5. Crop Region
            region_blob_path = None
            if bbox:
                try:
                    x0, y0, x1, y1 = bbox
                    if x1 > x0 and y1 > y0:
                        with Image.open(io.BytesIO(image_bytes)) as img:
                            crop = img.crop((x0, y0, x1, y1))
                            out = io.BytesIO()
                            crop.save(out, format="PNG")
                            region_data = out.getvalue()
                            
                            region_blob_path = f"{prefix}/visual_regions/{visual_asset_id}/region-{idx:03d}.png"
                            blob_provider.put_blob(
                                region_blob_path,
                                region_data,
                                content_type="image/png",
                                run_id=run_id,
                                ingest_batch_id=ingest_batch_id
                            )
                except Exception:
                    pass

            region_id = str(uuid4())
            region_evidence_ref = f"visual_region::{region_id}::crop"
            region_evidence_ref_id = _ensure_evidence_ref_row(region_evidence_ref, run_id=run_id)
            region_meta = {
                "region_blob_path": region_blob_path,
                "polygon": mask.get("polygon"),
                "confidence": mask.get("confidence"),
                "evidence_ref": region_evidence_ref,
            }
            
            _db_execute(
                """
                INSERT INTO visual_asset_regions (
                  id, visual_asset_id, run_id, region_type, bbox, bbox_quality,
                  mask_id, caption_text, evidence_ref_id, metadata_jsonb, created_at
                )
                VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s, %s::uuid, %s, %s::uuid, %s::jsonb, %s)
                """,
                (
                    region_id,
                    visual_asset_id,
                    run_id,
                    "mask_crop",
                    json.dumps(bbox, ensure_ascii=False) if bbox else None,
                    bbox_quality,
                    mask_id,
                    caption,
                    region_evidence_ref_id,
                    json.dumps(region_meta, ensure_ascii=False),
                    _utc_now(),
                ),
            )
            region_total += 1

    return mask_total, region_total
