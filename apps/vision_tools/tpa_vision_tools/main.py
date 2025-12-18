from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import cv2  # type: ignore
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from PIL import Image


def _b64decode(data: str) -> bytes:
    try:
        return base64.b64decode(data, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 input") from exc


def _image_from_b64_png_or_jpg(image_base64: str) -> Image.Image:
    raw = _b64decode(image_base64)
    try:
        return Image.open(BytesIO(raw)).convert("RGBA")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Unsupported or corrupt image") from exc


def _png_b64_from_rgba_array(arr_rgba: np.ndarray) -> str:
    img = Image.fromarray(arr_rgba.astype(np.uint8), mode="RGBA")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@dataclass(frozen=True)
class MaskResult:
    bbox: list[int]
    polygon: list[list[int]]
    mask_png_base64: str


def _largest_contour_mask(image_rgba: np.ndarray) -> MaskResult | None:
    rgb = cv2.cvtColor(image_rgba, cv2.COLOR_RGBA2RGB)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # Cheap, CPU-only heuristic: find the dominant high-contrast contour.
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Prefer "ink" as foreground. If background is selected, invert.
    if np.mean(thresh) > 127:
        thresh = cv2.bitwise_not(thresh)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    if area < 10.0:
        return None

    x, y, w, h = cv2.boundingRect(largest)
    bbox = [int(x), int(y), int(x + w), int(y + h)]

    mask = np.zeros((image_rgba.shape[0], image_rgba.shape[1]), dtype=np.uint8)
    cv2.drawContours(mask, [largest], -1, color=255, thickness=-1)

    rgba = np.zeros_like(image_rgba)
    rgba[..., 0] = 255
    rgba[..., 1] = 255
    rgba[..., 2] = 255
    rgba[..., 3] = mask

    polygon = [[int(pt[0][0]), int(pt[0][1])] for pt in largest]
    return MaskResult(bbox=bbox, polygon=polygon, mask_png_base64=_png_b64_from_rgba_array(rgba))


class SegmentRequest(BaseModel):
    image_base64: str = Field(..., description="PNG/JPEG base64. Use a screenshot or plan raster.")
    prompts: dict[str, Any] | None = Field(
        default=None,
        description="Optional prompts (labels/points/boxes). This heuristic implementation may ignore prompts.",
    )


class SegmentResponse(BaseModel):
    tool: str
    mode: str
    masks: list[dict[str, Any]]
    limitations_text: str


class VectorizeRequest(BaseModel):
    mask_png_base64: str | None = Field(
        default=None,
        description="RGBA PNG base64 where alpha channel encodes the mask. If omitted, `image_base64` must be provided.",
    )
    image_base64: str | None = Field(default=None, description="Fallback: segment first, then vectorize.")


class VectorizeResponse(BaseModel):
    tool: str
    mode: str
    features_geojson: dict[str, Any]
    limitations_text: str


app = FastAPI(title="TPA Vision Tools (Scaffold)", version="0.0.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/segment", response_model=SegmentResponse)
def segment(req: SegmentRequest) -> SegmentResponse:
    image = _image_from_b64_png_or_jpg(req.image_base64)
    arr = np.array(image)

    out = _largest_contour_mask(arr)
    masks: list[dict[str, Any]] = []
    if out is not None:
        masks.append(
            {
                "bbox": out.bbox,
                "polygon": out.polygon,
                "mask_png_base64": out.mask_png_base64,
                "confidence": None,
            }
        )

    return SegmentResponse(
        tool="vision_tools",
        mode=os.environ.get("TOOL_MODE", "segmentation"),
        masks=masks,
        limitations_text=(
            "CPU-only heuristic segmentation (largest contour). Not SAM2. "
            "Use this as a safe fallback; for production-grade plan/photo segmentation, "
            "replace with a SAM2-backed implementation and preserve ToolRun provenance."
        ),
    )


@app.post("/vectorize", response_model=VectorizeResponse)
def vectorize(req: VectorizeRequest) -> VectorizeResponse:
    if not req.mask_png_base64 and not req.image_base64:
        raise HTTPException(status_code=400, detail="Provide either mask_png_base64 or image_base64")

    if req.mask_png_base64:
        raw = _b64decode(req.mask_png_base64)
        img = Image.open(BytesIO(raw)).convert("RGBA")
        arr = np.array(img)
        alpha = arr[..., 3]
        mask = (alpha > 0).astype(np.uint8) * 255
    else:
        # Segment first (heuristic)
        image = _image_from_b64_png_or_jpg(req.image_base64 or "")
        arr2 = np.array(image)
        seg = _largest_contour_mask(arr2)
        if seg is None:
            mask = np.zeros((arr2.shape[0], arr2.shape[1]), dtype=np.uint8)
        else:
            raw = _b64decode(seg.mask_png_base64)
            img = Image.open(BytesIO(raw)).convert("RGBA")
            arr = np.array(img)
            alpha = arr[..., 3]
            mask = (alpha > 0).astype(np.uint8) * 255

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    features: list[dict[str, Any]] = []
    for c in contours[:25]:
        if cv2.contourArea(c) < 10.0:
            continue
        coords = [[int(pt[0][0]), int(pt[0][1])] for pt in c]
        if coords and coords[0] != coords[-1]:
            coords.append(coords[0])
        features.append(
            {
                "type": "Feature",
                "properties": {"source": "mask_contour"},
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            }
        )

    return VectorizeResponse(
        tool="vision_tools",
        mode=os.environ.get("TOOL_MODE", "vectorization"),
        features_geojson={"type": "FeatureCollection", "features": features},
        limitations_text=(
            "Raster→vector contour extraction in image pixel coordinates. "
            "This is not georeferenced; downstream registration (Transform/ProjectionArtifact) "
            "must supply spatial frame mapping and uncertainty."
        ),
    )

