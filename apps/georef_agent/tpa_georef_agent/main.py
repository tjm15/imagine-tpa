from __future__ import annotations

import base64
import io
import math
import os
import re
from io import BytesIO
from typing import Any
from uuid import uuid4
from urllib.parse import urlparse

import httpx
import numpy as np
import pytesseract
import rasterio
from pyproj import Transformer
from rasterio.control import GroundControlPoint
from rasterio.io import MemoryFile
from fastapi import FastAPI, HTTPException
from minio import Minio
from pydantic import BaseModel, Field
from PIL import Image, ImageFilter


def _decode_image(image_base64: str) -> tuple[bytes, int, int]:
    if "base64," in image_base64:
        image_base64 = image_base64.split("base64,", 1)[1]
    try:
        raw = base64.b64decode(image_base64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid_base64") from exc
    try:
        with Image.open(BytesIO(raw)) as img:
            width, height = img.size
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid_image") from exc
    return raw, int(width), int(height)


def _minio_client() -> Minio:
    endpoint = os.environ.get("TPA_S3_ENDPOINT")
    access_key = os.environ.get("TPA_S3_ACCESS_KEY")
    secret_key = os.environ.get("TPA_S3_SECRET_KEY")
    if not endpoint or not access_key or not secret_key:
        raise HTTPException(status_code=500, detail="minio_unconfigured")
    parsed = urlparse(endpoint)
    host = parsed.netloc or parsed.path
    secure = parsed.scheme == "https"
    return Minio(host, access_key=access_key, secret_key=secret_key, secure=secure)


def _ensure_bucket(client: Minio, bucket: str) -> None:
    try:
        exists = client.bucket_exists(bucket)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"minio_bucket_check_failed:{exc}") from exc
    if exists:
        return
    try:
        client.make_bucket(bucket)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"minio_bucket_create_failed:{exc}") from exc


def _upload_bytes(*, client: Minio, bucket: str, blob_path: str, data: bytes, content_type: str) -> None:
    try:
        data_stream = io.BytesIO(data)
        client.put_object(bucket, blob_path, data_stream, length=len(data), content_type=content_type)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"minio_upload_failed:{exc}") from exc


def _macro_base_url() -> str | None:
    return os.environ.get("TPA_GEOREF_MACRO_BASE_URL")


def _rmse_threshold() -> float:
    raw = os.environ.get("TPA_GEOREF_RMSE_THRESHOLD", "10")
    try:
        return float(raw)
    except Exception:  # noqa: BLE001
        return 10.0


def _reference_layer() -> str:
    return os.environ.get("TPA_GEOREF_REFERENCE_LAYER", "osm")


def _macro_call(path: str, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    base_url = _macro_base_url()
    if not base_url:
        return None, ["macro_unconfigured"]
    url = base_url.rstrip("/") + path
    try:
        with httpx.Client(timeout=None) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return None, [f"macro_call_failed:{exc}"]
    if not isinstance(data, dict):
        return None, ["macro_invalid_response"]
    return data, []


def _artifact_extension(artifact_type: str) -> tuple[str, str]:
    normalized = artifact_type.lower()
    if "tif" in normalized:
        return "tif", "image/tiff"
    if "png" in normalized or "overlay" in normalized:
        return "png", "image/png"
    if "jpeg" in normalized or "jpg" in normalized:
        return "jpg", "image/jpeg"
    return "bin", "application/octet-stream"


def _store_artifact(*, visual_asset_id: str, artifact_type: str, data: bytes) -> str:
    bucket = os.environ.get("TPA_S3_BUCKET") or "tpa"
    client = _minio_client()
    _ensure_bucket(client, bucket)
    ext, content_type = _artifact_extension(artifact_type)
    blob_path = f"georef/{visual_asset_id}/{uuid4()}.{ext}"
    _upload_bytes(client=client, bucket=bucket, blob_path=blob_path, data=data, content_type=content_type)
    return blob_path


def _parse_coord_from_text(text: str) -> tuple[float, float] | None:
    cleaned = text.strip().upper().replace(",", " ")
    if not cleaned:
        return None

    matches = re.findall(r"([EN])\s*([0-9]{5,7})", cleaned)
    if matches:
        easting = None
        northing = None
        for axis, value in matches:
            if axis == "E":
                easting = float(value)
            elif axis == "N":
                northing = float(value)
        if easting is not None and northing is not None:
            return easting, northing

    nums = re.findall(r"[0-9]{5,7}", cleaned)
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    return None


def _extract_candidate_gcps(image: Image.Image) -> tuple[list[CandidateGcp], str]:
    ocr = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    gcps: list[CandidateGcp] = []
    text_items = ocr.get("text", []) if isinstance(ocr, dict) else []
    for idx, text in enumerate(text_items):
        if not isinstance(text, str):
            continue
        coord = _parse_coord_from_text(text)
        if coord is None:
            continue
        try:
            left = float(ocr["left"][idx])
            top = float(ocr["top"][idx])
            width = float(ocr["width"][idx])
            height = float(ocr["height"][idx])
            conf_raw = ocr.get("conf", ["0"])[idx]
            conf_val = float(conf_raw) if isinstance(conf_raw, (int, float, str)) else 0.0
        except Exception:  # noqa: BLE001
            continue
        pixel = [left + width / 2.0, top + height / 2.0]
        gcps.append(CandidateGcp(pixel=pixel, world_guess=[coord[0], coord[1]], confidence=max(min(conf_val / 100.0, 1.0), 0.0)))
    limitations = "OCR-derived GCPs; verify coordinate labels before relying on results."
    return gcps, limitations


def _fetch_osm_highways(*, south: float, west: float, north: float, east: float) -> tuple[list[list[tuple[float, float]]], str | None]:
    overpass_url = os.environ.get("TPA_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
    query = f"""
[out:json];
(
  way["highway"]({south},{west},{north},{east});
);
out geom;
"""
    try:
        with httpx.Client(timeout=None) as client:
            resp = client.post(overpass_url, data=query)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return [], f"osm_query_failed:{exc}"

    elements = data.get("elements") if isinstance(data, dict) else None
    if not isinstance(elements, list):
        return [], "osm_invalid_response"

    lines: list[list[tuple[float, float]]] = []
    for el in elements:
        geom = el.get("geometry") if isinstance(el, dict) else None
        if not isinstance(geom, list):
            continue
        coords: list[tuple[float, float]] = []
        for pt in geom:
            if not isinstance(pt, dict):
                continue
            lat = pt.get("lat")
            lon = pt.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                coords.append((lon, lat))
        if len(coords) >= 2:
            lines.append(coords)
    return lines, None


def _osm_alignment_score(
    *,
    image: Image.Image,
    transform: rasterio.Affine,
    target_epsg: int,
) -> tuple[float | None, dict[str, Any]]:
    width, height = image.size
    corners = [
        transform * (0, 0),
        transform * (width, 0),
        transform * (0, height),
        transform * (width, height),
    ]
    xs = [pt[0] for pt in corners]
    ys = [pt[1] for pt in corners]
    if not xs or not ys:
        return None, {"reason": "corner_transform_failed"}

    to_latlon = Transformer.from_crs(f"EPSG:{target_epsg}", "EPSG:4326", always_xy=True)
    west, south = to_latlon.transform(min(xs), min(ys))
    east, north = to_latlon.transform(max(xs), max(ys))

    lines, err = _fetch_osm_highways(south=south, west=west, north=north, east=east)
    if err:
        return None, {"reason": err}
    if not lines:
        return None, {"reason": "osm_empty"}

    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_np = np.array(edges)
    edge_mask = edge_np > 20

    to_target = Transformer.from_crs("EPSG:4326", f"EPSG:{target_epsg}", always_xy=True)
    inv_transform = ~transform

    hits = 0
    total = 0
    for line in lines:
        for idx, (lon, lat) in enumerate(line):
            if idx % 5 != 0:
                continue
            x, y = to_target.transform(lon, lat)
            col, row = inv_transform * (x, y)
            col_i = int(round(col))
            row_i = int(round(row))
            if 0 <= col_i < width and 0 <= row_i < height:
                total += 1
                if edge_mask[row_i, col_i]:
                    hits += 1

    if total == 0:
        return None, {"reason": "osm_no_samples"}
    return hits / total, {"samples": total, "hits": hits, "osm_lines": len(lines)}


class CandidateGcp(BaseModel):
    pixel: list[float] = Field(..., description="Image pixel coordinate [x, y].")
    world_guess: list[float] = Field(..., description="World coordinate guess [x, y].")
    confidence: float | None = None


class ControlPoint(BaseModel):
    src: dict[str, float] = Field(..., description="Image coordinate with keys x,y.")
    dst: dict[str, float] = Field(..., description="World coordinate with keys x,y.")
    residual: float | None = None
    weight: float | None = None


class GeorefTransform(BaseModel):
    method: str
    matrix: list[list[float]]
    matrix_shape: list[int]
    uncertainty_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    control_points: list[ControlPoint] | None = None


class ProjectionArtifact(BaseModel):
    artifact_type: str
    artifact_path: str
    evidence_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AutoGeorefRequest(BaseModel):
    visual_asset_id: str
    asset_type: str | None = None
    asset_subtype: str | None = None
    target_epsg: int = 27700
    image_base64: str
    redline_mask_base64: str | None = None
    redline_mask_id: str | None = None
    canonical_facts: dict[str, Any] = Field(default_factory=dict)
    asset_specific_facts: dict[str, Any] = Field(default_factory=dict)


class AutoGeorefResponse(BaseModel):
    ok: bool
    status: str
    attempts: int
    errors: list[str]
    limitations_text: str
    transform: GeorefTransform | None = None
    control_points: list[ControlPoint] = Field(default_factory=list)
    projection_artifacts: list[ProjectionArtifact] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ExportMapObservationRequest(BaseModel):
    image_base64: str
    target_epsg: int | None = None
    extent: dict[str, Any] | None = None
    layers_on: list[str] | None = None


class ExportMapObservationResponse(BaseModel):
    ok: bool
    observation_png_base64: str | None = None
    limitations_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DetectCandidateGcpsRequest(BaseModel):
    image_base64: str
    redline_mask_base64: str | None = None
    method: str = "auto"
    target_epsg: int = 27700


class DetectCandidateGcpsResponse(BaseModel):
    ok: bool
    gcps: list[CandidateGcp]
    limitations_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApplyGcpsRequest(BaseModel):
    image_base64: str
    gcps: list[CandidateGcp]
    method: str = "affine"
    target_epsg: int = 27700


class ApplyGcpsResponse(BaseModel):
    ok: bool
    status: str
    transform: GeorefTransform | None = None
    errors: list[str]
    limitations_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluateGeorefRequest(BaseModel):
    image_base64: str
    target_epsg: int = 27700
    metrics: list[str] = Field(default_factory=list)


class EvaluateGeorefResponse(BaseModel):
    ok: bool
    metrics: dict[str, Any]
    limitations_text: str


class PublishOutputsRequest(BaseModel):
    artifact_base64: str
    artifact_type: str = "geotiff"
    metadata: dict[str, Any] = Field(default_factory=dict)


class PublishOutputsResponse(BaseModel):
    ok: bool
    artifact_path: str
    metadata: dict[str, Any]
    limitations_text: str


app = FastAPI(title="TPA Georef Agent", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auto-georef", response_model=AutoGeorefResponse)
def auto_georef(req: AutoGeorefRequest) -> AutoGeorefResponse:
    _, width, height = _decode_image(req.image_base64)
    attempts = 0
    errors: list[str] = []
    projection_artifacts: list[ProjectionArtifact] = []
    control_points: list[ControlPoint] = []
    metrics: dict[str, Any] = {
        "image_width": width,
        "image_height": height,
        "target_epsg": req.target_epsg,
        "asset_type": req.asset_type,
        "redline_mask_provided": bool(req.redline_mask_base64),
        "reference_layer": _reference_layer(),
    }
    provenance: dict[str, Any] = {"engine": "tpa-georef-agent", "policy": "closed-loop"}

    if isinstance(req.redline_mask_base64, str):
        try:
            mask_bytes, _, _ = _decode_image(req.redline_mask_base64)
            path = _store_artifact(
                visual_asset_id=req.visual_asset_id,
                artifact_type="redline_mask",
                data=mask_bytes,
            )
            projection_artifacts.append(
                ProjectionArtifact(
                    artifact_type="redline_mask",
                    artifact_path=path,
                    metadata={"source": "redline_mask", "mask_id": req.redline_mask_id},
                )
            )
        except HTTPException as exc:
            errors.append(f"redline_mask_store_failed:{exc.detail}")

    if not _macro_base_url():
        return AutoGeorefResponse(
            ok=False,
            status="needs_manual_anchors",
            attempts=1,
            errors=["macro_unconfigured"],
            limitations_text=(
                "Auto-georef requires a macro toolchain (QGIS MCP wrapper). "
                "Set TPA_GEOREF_MACRO_BASE_URL to enable agentic georeferencing."
            ),
            metrics=metrics,
            provenance={**provenance, "mode": "stub"},
        )

    attempts += 1
    observation, obs_errors = _macro_call(
        "/macros/export-map-observation",
        {
            "image_base64": req.image_base64,
            "target_epsg": req.target_epsg,
        },
    )
    errors.extend(obs_errors)
    if observation and isinstance(observation.get("observation_png_base64"), str):
        obs_bytes, _, _ = _decode_image(observation["observation_png_base64"])
        try:
            path = _store_artifact(
                visual_asset_id=req.visual_asset_id,
                artifact_type="overlay_png",
                data=obs_bytes,
            )
            projection_artifacts.append(
                ProjectionArtifact(
                    artifact_type="overlay_png",
                    artifact_path=path,
                    metadata={"source": "export-map-observation"},
                )
            )
        except HTTPException as exc:
            errors.append(f"artifact_store_failed:{exc.detail}")

    gcps_resp, gcps_errors = _macro_call(
        "/macros/detect-candidate-gcps",
        {
            "image_base64": req.image_base64,
            "redline_mask_base64": req.redline_mask_base64,
            "method": "auto",
            "target_epsg": req.target_epsg,
        },
    )
    errors.extend(gcps_errors)
    gcps = gcps_resp.get("gcps") if isinstance(gcps_resp, dict) else None
    if not isinstance(gcps, list) or not gcps:
        errors.append("no_gcps_detected")
        return AutoGeorefResponse(
            ok=False,
            status="needs_manual_anchors",
            attempts=attempts,
            errors=errors,
            limitations_text="No candidate GCPs detected; manual anchors required.",
            projection_artifacts=projection_artifacts,
            metrics=metrics,
            provenance={**provenance, "mode": "macro"},
        )

    apply_resp, apply_errors = _macro_call(
        "/macros/apply-gcps",
        {
            "image_base64": req.image_base64,
            "redline_mask_base64": req.redline_mask_base64,
            "gcps": gcps,
            "method": "affine",
            "target_epsg": req.target_epsg,
        },
    )
    errors.extend(apply_errors)
    transform_obj = apply_resp.get("transform") if isinstance(apply_resp, dict) else None

    if isinstance(apply_resp, dict):
        meta = apply_resp.get("metadata") if isinstance(apply_resp.get("metadata"), dict) else {}
        artifact_candidates = [
            ("geotiff", meta.get("geotiff_base64")),
            ("overlay_png", meta.get("overlay_png_base64")),
        ]
        for artifact_type, b64 in artifact_candidates:
            if isinstance(b64, str) and b64:
                try:
                    if "tif" in artifact_type:
                        if "base64," in b64:
                            b64 = b64.split("base64,", 1)[1]
                        data_bytes = base64.b64decode(b64, validate=True)
                    else:
                        data_bytes, _, _ = _decode_image(b64)
                    path = _store_artifact(
                        visual_asset_id=req.visual_asset_id,
                        artifact_type=artifact_type,
                        data=data_bytes,
                    )
                    projection_artifacts.append(
                        ProjectionArtifact(
                            artifact_type=artifact_type,
                            artifact_path=path,
                            metadata={"source": "apply-gcps"},
                        )
                    )
                except HTTPException as exc:
                    errors.append(f"artifact_store_failed:{exc.detail}")

    if isinstance(gcps, list):
        for item in gcps:
            try:
                if not isinstance(item, dict):
                    continue
                pixel = item.get("pixel")
                world = item.get("world_guess")
                if not (isinstance(pixel, list) and isinstance(world, list) and len(pixel) >= 2 and len(world) >= 2):
                    continue
                control_points.append(
                    ControlPoint(
                        src={"x": float(pixel[0]), "y": float(pixel[1])},
                        dst={"x": float(world[0]), "y": float(world[1])},
                    )
                )
            except Exception:  # noqa: BLE001
                continue

    if not isinstance(transform_obj, dict):
        errors.append("transform_missing")
        return AutoGeorefResponse(
            ok=False,
            status="warp_failed",
            attempts=attempts,
            errors=errors,
            limitations_text="Warp failed; no transform returned from macro toolchain.",
            control_points=control_points,
            projection_artifacts=projection_artifacts,
            metrics=metrics,
            provenance={**provenance, "mode": "macro"},
        )

    evaluate_resp, eval_errors = _macro_call(
        "/macros/evaluate-georef",
        {"image_base64": req.image_base64, "target_epsg": req.target_epsg, "metrics": ["rmse", "alignment"]},
    )
    errors.extend(eval_errors)
    if isinstance(evaluate_resp, dict):
        metrics["evaluation"] = evaluate_resp.get("metrics") or {}

    rmse_threshold = _rmse_threshold()
    rmse = None
    if isinstance(apply_resp, dict):
        meta = apply_resp.get("metadata") if isinstance(apply_resp.get("metadata"), dict) else {}
        if isinstance(meta.get("rmse"), (int, float)):
            rmse = float(meta["rmse"])

    metrics["rmse"] = rmse
    metrics["rmse_threshold"] = rmse_threshold

    transform = GeorefTransform(**transform_obj)
    ok = rmse is not None and rmse <= rmse_threshold
    status = "success" if ok else "needs_manual_anchors"
    if not ok:
        errors.append("rmse_threshold_failed")
    limitations_text = (
        "RMSE threshold met; verify alignment before relying on overlays."
        if ok
        else "RMSE exceeds threshold or unavailable; manual anchors required."
    )
    return AutoGeorefResponse(
        ok=ok,
        status=status,
        attempts=attempts,
        errors=errors,
        limitations_text=limitations_text,
        transform=transform,
        control_points=control_points or (transform.control_points or []),
        projection_artifacts=projection_artifacts,
        metrics=metrics,
        provenance={
            **provenance,
            "mode": "macro",
            "macro_base_url": _macro_base_url(),
            "reference_layer": _reference_layer(),
        },
    )


@app.post("/macros/export-map-observation", response_model=ExportMapObservationResponse)
def export_map_observation(req: ExportMapObservationRequest) -> ExportMapObservationResponse:
    _decode_image(req.image_base64)
    return ExportMapObservationResponse(
        ok=True,
        observation_png_base64=req.image_base64,
        limitations_text="Observation passthrough; no map rendering applied.",
        metadata={"target_epsg": req.target_epsg, "layers_on": req.layers_on, "extent": req.extent},
    )


@app.post("/macros/detect-candidate-gcps", response_model=DetectCandidateGcpsResponse)
def detect_candidate_gcps(req: DetectCandidateGcpsRequest) -> DetectCandidateGcpsResponse:
    raw, _, _ = _decode_image(req.image_base64)
    try:
        with Image.open(BytesIO(raw)) as img:
            img = img.convert("RGB")
            gcps, limitations = _extract_candidate_gcps(img)
    except Exception as exc:  # noqa: BLE001
        return DetectCandidateGcpsResponse(
            ok=False,
            gcps=[],
            limitations_text=f"OCR failed: {exc}",
            metadata={"method": req.method, "target_epsg": req.target_epsg},
        )

    ok = bool(gcps)
    return DetectCandidateGcpsResponse(
        ok=ok,
        gcps=gcps,
        limitations_text=limitations,
        metadata={"method": req.method, "target_epsg": req.target_epsg, "gcps": len(gcps)},
    )


@app.post("/macros/apply-gcps", response_model=ApplyGcpsResponse)
def apply_gcps(req: ApplyGcpsRequest) -> ApplyGcpsResponse:
    raw, width, height = _decode_image(req.image_base64)
    if not req.gcps:
        return ApplyGcpsResponse(
            ok=False,
            status="no_gcps",
            transform=None,
            errors=["gcps_required"],
            limitations_text="Cannot warp without control points.",
            metadata={"method": req.method, "target_epsg": req.target_epsg},
        )

    try:
        with Image.open(BytesIO(raw)) as img:
            img = img.convert("RGB")
            image_np = np.array(img)
    except Exception as exc:  # noqa: BLE001
        return ApplyGcpsResponse(
            ok=False,
            status="image_invalid",
            transform=None,
            errors=[f"image_open_failed:{exc}"],
            limitations_text="Image could not be decoded for georeferencing.",
            metadata={"method": req.method, "target_epsg": req.target_epsg},
        )

    gcp_objs: list[GroundControlPoint] = []
    control_points: list[ControlPoint] = []
    for gcp in req.gcps:
        try:
            pixel = gcp.get("pixel") if isinstance(gcp, dict) else None
            world = gcp.get("world_guess") if isinstance(gcp, dict) else None
            if not (isinstance(pixel, list) and isinstance(world, list) and len(pixel) >= 2 and len(world) >= 2):
                continue
            col = float(pixel[0])
            row = float(pixel[1])
            x = float(world[0])
            y = float(world[1])
        except Exception:  # noqa: BLE001
            continue
        gcp_objs.append(GroundControlPoint(row=row, col=col, x=x, y=y))
        control_points.append(ControlPoint(src={"x": col, "y": row}, dst={"x": x, "y": y}))

    if len(gcp_objs) < 3:
        return ApplyGcpsResponse(
            ok=False,
            status="insufficient_gcps",
            transform=None,
            errors=["gcps_insufficient"],
            limitations_text="At least three control points are required for an affine transform.",
            metadata={"method": req.method, "target_epsg": req.target_epsg, "gcps": len(gcp_objs)},
        )

    try:
        transform = rasterio.transform.from_gcps(gcp_objs)
    except Exception as exc:  # noqa: BLE001
        return ApplyGcpsResponse(
            ok=False,
            status="transform_failed",
            transform=None,
            errors=[f"transform_failed:{exc}"],
            limitations_text="Failed to compute georeferencing transform.",
            metadata={"method": req.method, "target_epsg": req.target_epsg, "gcps": len(gcp_objs)},
        )

    residuals: list[float] = []
    for cp in control_points:
        world_x, world_y = transform * (cp.src["x"], cp.src["y"])
        resid = math.hypot(world_x - cp.dst["x"], world_y - cp.dst["y"])
        cp.residual = resid
        residuals.append(resid)

    rmse = math.sqrt(sum(r * r for r in residuals) / len(residuals)) if residuals else None

    alignment_score = None
    alignment_meta: dict[str, Any] = {}
    try:
        alignment_score, alignment_meta = _osm_alignment_score(
            image=Image.fromarray(image_np),
            transform=transform,
            target_epsg=req.target_epsg,
        )
    except Exception as exc:  # noqa: BLE001
        alignment_meta = {"reason": f"alignment_failed:{exc}"}

    matrix = [
        [float(transform.a), float(transform.b), float(transform.c)],
        [float(transform.d), float(transform.e), float(transform.f)],
        [0.0, 0.0, 1.0],
    ]
    inverse_matrix = None
    try:
        inv = np.linalg.inv(np.array(matrix))
        inverse_matrix = inv.tolist()
    except Exception:  # noqa: BLE001
        inverse_matrix = None

    geotiff_b64 = None
    try:
        with MemoryFile() as memfile:
            with memfile.open(
                driver="GTiff",
                height=height,
                width=width,
                count=3,
                dtype=image_np.dtype,
                crs=f"EPSG:{req.target_epsg}",
                transform=transform,
            ) as dst:
                dst.write(np.transpose(image_np, (2, 0, 1)))
            geotiff_b64 = base64.b64encode(memfile.read()).decode("ascii")
    except Exception:  # noqa: BLE001
        geotiff_b64 = None

    transform_obj = GeorefTransform(
        method=req.method,
        matrix=matrix,
        matrix_shape=[3, 3],
        uncertainty_score=rmse,
        metadata={
            "rmse": rmse,
            "alignment_score": alignment_score,
            "alignment_meta": alignment_meta,
            "gcps_used": len(gcp_objs),
            "target_epsg": req.target_epsg,
            "inverse_matrix": inverse_matrix,
            "reference_layer": _reference_layer(),
        },
        control_points=control_points,
    )

    metadata = {
        "method": req.method,
        "target_epsg": req.target_epsg,
        "gcps": len(gcp_objs),
        "rmse": rmse,
        "alignment_score": alignment_score,
        "alignment_meta": alignment_meta,
        "geotiff_base64": geotiff_b64,
    }

    return ApplyGcpsResponse(
        ok=True,
        status="success",
        transform=transform_obj,
        errors=[],
        limitations_text="Affine transform derived from OCR-detected control points; verify alignment.",
        metadata=metadata,
    )


@app.post("/macros/evaluate-georef", response_model=EvaluateGeorefResponse)
def evaluate_georef(req: EvaluateGeorefRequest) -> EvaluateGeorefResponse:
    _decode_image(req.image_base64)
    return EvaluateGeorefResponse(
        ok=False,
        metrics={"rmse": None, "metrics_requested": req.metrics},
        limitations_text="No evaluation metrics available without georeferenced output.",
    )


@app.post("/macros/publish-outputs", response_model=PublishOutputsResponse)
def publish_outputs(req: PublishOutputsRequest) -> PublishOutputsResponse:
    try:
        raw = base64.b64decode(req.artifact_base64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid_base64") from exc
    artifact_path = _store_artifact(
        visual_asset_id=req.metadata.get("visual_asset_id", "unknown"),
        artifact_type=req.artifact_type,
        data=raw,
    )
    return PublishOutputsResponse(
        ok=True,
        artifact_path=artifact_path,
        metadata=req.metadata,
        limitations_text="Stored in object storage; geospatial validity depends on upstream transform.",
    )
