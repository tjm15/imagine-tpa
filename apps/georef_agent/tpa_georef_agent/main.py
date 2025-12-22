from __future__ import annotations

import base64
import io
import os
from io import BytesIO
from typing import Any
from uuid import uuid4
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from minio import Minio
from pydantic import BaseModel, Field
from PIL import Image


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
    }
    provenance: dict[str, Any] = {"engine": "tpa-georef-agent", "policy": "closed-loop"}

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

    transform = GeorefTransform(**transform_obj)
    return AutoGeorefResponse(
        ok=True,
        status="success",
        attempts=attempts,
        errors=errors,
        limitations_text="Macro toolchain executed; verify alignment and uncertainty before relying on overlays.",
        transform=transform,
        control_points=control_points or (transform.control_points or []),
        projection_artifacts=projection_artifacts,
        metrics=metrics,
        provenance={**provenance, "mode": "macro", "macro_base_url": _macro_base_url()},
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
    _decode_image(req.image_base64)
    return DetectCandidateGcpsResponse(
        ok=False,
        gcps=[],
        limitations_text="GCP auto-detection not configured; integrate QGIS macros for grid/junction detection.",
        metadata={"method": req.method, "target_epsg": req.target_epsg},
    )


@app.post("/macros/apply-gcps", response_model=ApplyGcpsResponse)
def apply_gcps(req: ApplyGcpsRequest) -> ApplyGcpsResponse:
    _decode_image(req.image_base64)
    if not req.gcps:
        return ApplyGcpsResponse(
            ok=False,
            status="no_gcps",
            transform=None,
            errors=["gcps_required"],
            limitations_text="Cannot warp without control points.",
            metadata={"method": req.method, "target_epsg": req.target_epsg},
        )
    return ApplyGcpsResponse(
        ok=False,
        status="warp_unavailable",
        transform=None,
        errors=["warp_unimplemented"],
        limitations_text="Warping not implemented in stub service.",
        metadata={"method": req.method, "target_epsg": req.target_epsg, "gcps": len(req.gcps)},
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
