from __future__ import annotations

import base64
import os
from contextlib import asynccontextmanager
from io import BytesIO
from threading import Semaphore
from typing import Any

import cv2  # type: ignore
import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from PIL import Image

# Import SAM2
try:
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor
    from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
except ImportError:
    # Fallback for build environments where SAM2 might not be fully installed yet
    SAM2ImagePredictor = None
    SAM2AutomaticMaskGenerator = None
    build_sam2 = None


# Global model state
models = {}
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default

# Limit concurrent SAM2 requests to avoid GPU OOM.
_SAM2_MAX_INFLIGHT = max(1, _int_env("TPA_SAM2_MAX_INFLIGHT", 1))
_SAM2_SEMAPHORE = Semaphore(_SAM2_MAX_INFLIGHT)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load SAM2 model on startup
    if build_sam2:
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"Loading SAM2 model on {device}...")
            
            # Paths inside the container (see Dockerfile)
            checkpoint = "/app/checkpoints/sam2_hiera_large.pt"
            config = "sam2_hiera_l.yaml"
            
            if os.path.exists(checkpoint):
                # Build the model
                sam2_model = build_sam2(config, checkpoint, device=device, apply_postprocessing=False)
                
                # We initialize both the predictor (for prompts) and generator (for auto)
                # Note: They share the underlying model, so memory overhead is just the wrapper.
                models["predictor"] = SAM2ImagePredictor(sam2_model)
                models["generator"] = SAM2AutomaticMaskGenerator(sam2_model)
                print("SAM2 model loaded successfully.")
            else:
                print(f"SAM2 checkpoint not found at {checkpoint}. Running in placeholder mode.")
        except Exception as e:
            print(f"Failed to load SAM2: {e}")
    
    yield
    
    # Cleanup
    models.clear()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


app = FastAPI(title="TPA Vision Tools (SAM2)", version="0.1.0", lifespan=lifespan)


def _b64decode(data: str) -> bytes:
    try:
        return base64.b64decode(data, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 input") from exc


def _image_from_b64_png_or_jpg(image_base64: str) -> Image.Image:
    raw = _b64decode(image_base64)
    try:
        return Image.open(BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Unsupported or corrupt image") from exc


def _png_b64_from_rgba_array(arr_rgba: np.ndarray) -> str:
    img = Image.fromarray(arr_rgba.astype(np.uint8), mode="RGBA")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _mask_to_rgba_b64(mask_bool: np.ndarray) -> str:
    # Convert bool mask to RGBA PNG
    h, w = mask_bool.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[mask_bool, :] = [255, 255, 255, 255] # White mask
    return _png_b64_from_rgba_array(rgba)


def _largest_contour_mask(image_rgba: np.ndarray) -> dict[str, Any] | None:
    # Legacy OpenCV fallback if SAM2 is unavailable
    rgb = cv2.cvtColor(image_rgba, cv2.COLOR_RGBA2RGB)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.mean(thresh) > 127:
        thresh = cv2.bitwise_not(thresh)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 10.0:
        return None
    x, y, w, h = cv2.boundingRect(largest)
    mask = np.zeros((image_rgba.shape[0], image_rgba.shape[1]), dtype=np.uint8)
    cv2.drawContours(mask, [largest], -1, color=255, thickness=-1)
    return {
        "bbox": [int(x), int(y), int(x + w), int(y + h)],
        "polygon": [[int(pt[0][0]), int(pt[0][1])] for pt in largest],
        "mask": mask.astype(bool)
    }


class SegmentRequest(BaseModel):
    image_base64: str = Field(..., description="PNG/JPEG base64. Use a screenshot or plan raster.")
    prompts: dict[str, Any] | None = Field(
        default=None,
        description="Optional prompts: {'box': [x0, y0, x1, y1], 'point_coords': [[x,y]], 'point_labels': [1]}",
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


@app.get("/healthz")
def healthz() -> dict[str, str]:
    model_status = "loaded" if models.get("predictor") else "unloaded"
    return {"status": "ok", "sam2": model_status}


@app.post("/segment", response_model=SegmentResponse)
def segment(req: SegmentRequest) -> SegmentResponse:
    image_pil = _image_from_b64_png_or_jpg(req.image_base64)
    image_np = np.array(image_pil)
    
    masks_out: list[dict[str, Any]] = []
    mode = "sam2_hiera_large"
    
    if models.get("predictor") or models.get("generator"):
        # SAM2 Inference
        _SAM2_SEMAPHORE.acquire()
        try:
            if req.prompts and (req.prompts.get("box") or req.prompts.get("point_coords")):
                # Prompted segmentation
                predictor = models["predictor"]
                predictor.set_image(image_np)
                
                box = np.array(req.prompts["box"]) if req.prompts.get("box") else None
                points = np.array(req.prompts["point_coords"]) if req.prompts.get("point_coords") else None
                labels = np.array(req.prompts["point_labels"]) if req.prompts.get("point_labels") else None
                
                masks, scores, _ = predictor.predict(
                    point_coords=points,
                    point_labels=labels,
                    box=box,
                    multimask_output=True # Get 3 options, we pick best
                )
                
                # Pick best score
                best_idx = np.argmax(scores)
                best_mask = masks[best_idx]
                
                masks_out.append({
                    "bbox": req.prompts.get("box"), # Echo input or derived
                    "mask_png_base64": _mask_to_rgba_b64(best_mask),
                    "confidence": float(scores[best_idx]),
                    "polygon": [] # TODO: Extract poly from mask if needed
                })
                
            else:
                # Automatic segmentation
                generator = models["generator"]
                generated_masks = generator.generate(image_np)
                
                for m in generated_masks:
                    # Filter small garbage
                    if m["area"] < 500: 
                        continue
                        
                    masks_out.append({
                        "bbox": m["bbox"], # [x, y, w, h] in SAM format
                        "mask_png_base64": _mask_to_rgba_b64(m["segmentation"]),
                        "confidence": float(m["predicted_iou"]),
                        "polygon": m.get("point_coords", []) # SAM2 auto outputs some coords
                    })
                    
        except Exception as e:
            print(f"SAM2 inference failed: {e}")
            # Fall through to heuristic if SAM2 crashes on an edge case
            pass
        finally:
            _SAM2_SEMAPHORE.release()

    # Fallback if SAM2 failed or not loaded
    if not masks_out:
        mode = "cpu_heuristic_fallback"
        image_rgba = np.array(image_pil.convert("RGBA"))
        out = _largest_contour_mask(image_rgba)
        if out:
            masks_out.append({
                "bbox": out["bbox"],
                "polygon": out["polygon"],
                "mask_png_base64": _png_b64_from_rgba_array(Image.fromarray((out["mask"] * 255).astype(np.uint8))),
                "confidence": 0.5
            })

    return SegmentResponse(
        tool="vision_tools",
        mode=mode,
        masks=masks_out,
        limitations_text=(
            f"Using {mode}. "
            "SAM2 is preferred for complex scenes; heuristic used if model unavailable."
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
        # Extract alpha or if it's black/white, take R channel
        if arr.shape[2] == 4:
            mask = arr[..., 3]
        else:
            mask = arr[..., 0]
        mask = (mask > 127).astype(np.uint8) * 255
    else:
        # Segment first (heuristic fallback inside vectorize not recommended but supported)
        # In a real flow, call /segment first, then pass result here.
        image = _image_from_b64_png_or_jpg(req.image_base64 or "")
        arr2 = np.array(image.convert("RGBA"))
        out = _largest_contour_mask(arr2)
        if out is None:
            mask = np.zeros((arr2.shape[0], arr2.shape[1]), dtype=np.uint8)
        else:
            mask = (out["mask"] * 255).astype(np.uint8)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    features: list[dict[str, Any]] = []
    
    # Simple polygon approximation
    for c in contours[:50]: # Limit to 50 main features
        if cv2.contourArea(c) < 10.0:
            continue
        
        # Approximate to reduce points
        epsilon = 0.005 * cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, epsilon, True)
        
        coords = [[int(pt[0][0]), int(pt[0][1])] for pt in approx]
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
            "Raster→vector contour extraction (OpenCV). "
            "Coordinates are image pixels."
        ),
    )
