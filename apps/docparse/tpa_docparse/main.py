from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import time
from typing import Any
from uuid import uuid4
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse

from pypdf import PdfReader
from minio import Minio
from PIL import Image


app = FastAPI(title="TPA DocParse (ParseBundle v2)", version="0.2.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _minio_client() -> Minio:
    endpoint = os.environ.get("TPA_S3_ENDPOINT")
    access_key = os.environ.get("TPA_S3_ACCESS_KEY")
    secret_key = os.environ.get("TPA_S3_SECRET_KEY")
    if not endpoint or not access_key or not secret_key:
        raise HTTPException(status_code=500, detail="MinIO is not configured")
    parsed = urlparse(endpoint)
    host = parsed.netloc or parsed.path
    secure = parsed.scheme == "https"
    return Minio(host, access_key=access_key, secret_key=secret_key, secure=secure)


def _ensure_bucket(client: Minio, bucket: str) -> None:
    try:
        exists = client.bucket_exists(bucket)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"MinIO bucket check failed: {exc}") from exc
    if exists:
        return
    try:
        client.make_bucket(bucket)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"MinIO bucket create failed: {exc}") from exc


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _upload_bytes(*, client: Minio, bucket: str, blob_path: str, data: bytes, content_type: str) -> None:
    try:
        data_stream = io.BytesIO(data)
        client.put_object(bucket, blob_path, data_stream, length=len(data), content_type=content_type)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"MinIO upload failed: {exc}") from exc


def _as_data_url(data: bytes, content_type: str) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _strip_json_fence(text: str) -> str:
    if "```" not in text:
        return text
    cleaned = text
    cleaned = cleaned.replace("```json", "```")
    parts = cleaned.split("```")
    if len(parts) >= 2:
        return parts[1].strip()
    return cleaned


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = _strip_json_fence(text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def _call_llm_json(*, prompt: str, model_id: str | None, time_budget_seconds: float) -> tuple[dict[str, Any] | None, list[str]]:
    base_url = os.environ.get("TPA_LLM_BASE_URL")
    if not base_url:
        return None, ["llm_unconfigured"]
    model = model_id or os.environ.get("TPA_LLM_MODEL_ID") or "openai/gpt-oss-20b"
    timeout = min(max(time_budget_seconds, 2.0), 180.0)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 1400,
    }
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return None, [f"llm_request_failed:{exc}"]
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        return None, [f"llm_response_invalid:{exc}"]
    obj = _extract_json(content)
    if obj is None:
        return None, ["llm_json_parse_failed"]
    return obj, []


def _call_vlm_json(*, prompt: str, image_bytes: bytes, model_id: str | None, time_budget_seconds: float) -> tuple[dict[str, Any] | None, list[str]]:
    base_url = os.environ.get("TPA_VLM_BASE_URL")
    if not base_url:
        return None, ["vlm_unconfigured"]
    model = model_id or os.environ.get("TPA_VLM_MODEL_ID") or "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8"
    timeout = min(max(time_budget_seconds, 2.0), 240.0)
    data_url = _as_data_url(image_bytes, "image/png")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0.2,
        "max_tokens": 800,
    }
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return None, [f"vlm_request_failed:{exc}"]
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        return None, [f"vlm_response_invalid:{exc}"]
    obj = _extract_json(content)
    if obj is None:
        return None, ["vlm_json_parse_failed"]
    return obj, []


def _normalize_image_bytes(data: bytes) -> tuple[bytes, str, int | None, int | None]:
    try:
        with Image.open(io.BytesIO(data)) as img:
            out = io.BytesIO()
            img.convert("RGB").save(out, format="PNG")
            return out.getvalue(), "png", img.width, img.height
    except Exception:  # noqa: BLE001
        return data, "bin", None, None


def _extract_page_texts(reader: PdfReader, *, max_pages: int) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for idx, page in enumerate(reader.pages, start=1):
        if idx > max_pages:
            break
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        pages.append({"page_number": idx, "text": text})
    return pages


def _extract_images(reader: PdfReader, *, max_pages: int, max_visuals: int) -> list[dict[str, Any]]:
    visuals: list[dict[str, Any]] = []
    for idx, page in enumerate(reader.pages, start=1):
        if idx > max_pages:
            break
        if not getattr(page, "images", None):
            continue
        for image in page.images:
            if len(visuals) >= max_visuals:
                break
            raw = getattr(image, "data", None)
            if raw is None:
                continue
            normalized, ext, width, height = _normalize_image_bytes(raw)
            visuals.append(
                {
                    "page_number": idx,
                    "bytes": normalized,
                    "extension": ext,
                    "width": width,
                    "height": height,
                }
            )
    return visuals


def _lines_to_blocks(page_texts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    block_index = 0
    for page in page_texts:
        page_number = int(page.get("page_number") or 0)
        text = str(page.get("text") or "")
        if not text.strip():
            continue
        buf: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                if buf:
                    block_index += 1
                    blocks.append(
                        {
                            "block_id": f"b-{block_index:05d}",
                            "type": "unknown",
                            "text": " ".join(buf).strip(),
                            "page_number": page_number,
                            "section_path": None,
                            "bbox": None,
                        }
                    )
                    buf = []
                continue
            buf.append(line)
        if buf:
            block_index += 1
            blocks.append(
                {
                    "block_id": f"b-{block_index:05d}",
                    "type": "unknown",
                    "text": " ".join(buf).strip(),
                    "page_number": page_number,
                    "section_path": None,
                    "bbox": None,
                }
            )
    return blocks


def _chunk_blocks_for_llm(
    blocks: list[dict[str, Any]],
    *,
    max_blocks: int,
    max_chars: int,
) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for block in blocks:
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        snippet = text[:800]
        if current and (len(current) >= max_blocks or current_chars + len(snippet) > max_chars):
            groups.append(current)
            current = []
            current_chars = 0
        current.append(
            {
                "block_id": block.get("block_id"),
                "page_number": block.get("page_number"),
                "text": snippet,
            }
        )
        current_chars += len(snippet)
    if current:
        groups.append(current)
    return groups


def _annotate_blocks_with_llm(
    blocks: list[dict[str, Any]],
    *,
    llm_model_id: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not blocks:
        return blocks, [], [], [], []

    max_blocks = int(os.environ.get("TPA_DOCPARSE_LLM_BLOCKS", "60"))
    max_chars = int(os.environ.get("TPA_DOCPARSE_LLM_CHARS", "12000"))
    groups = _chunk_blocks_for_llm(blocks, max_blocks=max_blocks, max_chars=max_chars)

    block_annotations: dict[str, dict[str, Any]] = {}
    policy_headings: list[dict[str, Any]] = []
    standard_matrices: list[dict[str, Any]] = []
    scope_candidates: list[dict[str, Any]] = []
    tool_runs: list[dict[str, Any]] = []

    block_ref = {str(b.get("block_id")): b.get("evidence_ref") for b in blocks if b.get("block_id")}

    prompt = (
        "You are a planning document parsing instrument for UK Local Plans.\n"
        "Given blocks with block_id, page_number, and text, return ONLY valid JSON with:\n"
        "{\n"
        "  \"block_annotations\": [\n"
        "    {\"block_id\": \"...\", \"block_type\": \"heading|paragraph|bullets|table|caption|other\", \"section_path\": \"...\"}\n"
        "  ],\n"
        "  \"policy_headings\": [\n"
        "    {\"block_id\": \"...\", \"policy_code\": \"DM1\", \"policy_title\": \"...\", \"confidence_hint\": \"low|medium|high|unknown\", \"uncertainty_note\": \"...\"}\n"
        "  ],\n"
        "  \"standard_matrices\": [\n"
        "    {\"matrix_id\": \"...\", \"inputs\": [\"...\"], \"outputs\": [\"...\"], \"logic_type\": \"Lookup|Multiplication|Threshold|Other\", \"evidence_block_id\": \"...\"}\n"
        "  ],\n"
        "  \"scope_candidates\": [\n"
        "    {\n"
        "      \"id\": \"...\",\n"
        "      \"geography_refs\": [\"...\"],\n"
        "      \"development_types\": [\"...\"],\n"
        "      \"use_classes\": [\"...\"],\n"
        "      \"use_class_regime\": \"2020_Amendment|Pre_2020|Sui_Generis|unknown\",\n"
        "      \"temporal_scope\": {\"start_date\": null, \"end_date\": null, \"phasing_stage\": null},\n"
        "      \"conditions\": [\"...\"],\n"
        "      \"evidence_block_id\": \"...\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules: Use ONLY block_id values from the input blocks. Do not invent ids. "
        "If unsure, leave arrays empty or use \"unknown\" for use_class_regime."
    )

    for idx, group in enumerate(groups, start=1):
        started = time.time()
        obj, errs = _call_llm_json(
            prompt=prompt + "\n\n" + json.dumps({"blocks": group}, ensure_ascii=False),
            model_id=llm_model_id,
            time_budget_seconds=140.0,
        )
        elapsed = max(0.0, time.time() - started)
        tool_runs.append(
            {
                "tool_name": "llm_block_annotation",
                "status": "success" if obj else "error",
                "inputs": {"group_index": idx, "block_count": len(group)},
                "outputs": obj or {"errors": errs},
                "duration_seconds": elapsed,
                "limitations_text": "LLM parsing of block structure and policy scope; verify against source.",
            }
        )
        if not obj:
            continue

        annotations = obj.get("block_annotations") if isinstance(obj, dict) else None
        if isinstance(annotations, list):
            for item in annotations:
                if not isinstance(item, dict):
                    continue
                block_id = item.get("block_id")
                if not isinstance(block_id, str) or block_id not in block_ref:
                    continue
                block_annotations[block_id] = {
                    "block_type": item.get("block_type"),
                    "section_path": item.get("section_path"),
                }

        policy_items = obj.get("policy_headings") if isinstance(obj, dict) else None
        if isinstance(policy_items, list):
            for item in policy_items:
                if not isinstance(item, dict):
                    continue
                block_id = item.get("block_id")
                policy_code = item.get("policy_code")
                if not isinstance(block_id, str) or block_id not in block_ref:
                    continue
                if not isinstance(policy_code, str) or not policy_code.strip():
                    continue
                policy_headings.append(
                    {
                        "block_id": block_id,
                        "policy_code": policy_code.strip(),
                        "policy_title": item.get("policy_title") if isinstance(item.get("policy_title"), str) else None,
                        "confidence_hint": item.get("confidence_hint") if isinstance(item.get("confidence_hint"), str) else None,
                        "uncertainty_note": item.get("uncertainty_note") if isinstance(item.get("uncertainty_note"), str) else None,
                        "evidence_ref": block_ref.get(block_id),
                    }
                )

        matrices = obj.get("standard_matrices") if isinstance(obj, dict) else None
        if isinstance(matrices, list):
            for item in matrices:
                if not isinstance(item, dict):
                    continue
                inputs = item.get("inputs") if isinstance(item.get("inputs"), list) else []
                outputs = item.get("outputs") if isinstance(item.get("outputs"), list) else []
                inputs = [str(x) for x in inputs if isinstance(x, str)]
                outputs = [str(x) for x in outputs if isinstance(x, str)]
                if not inputs or not outputs:
                    continue
                matrix_id = item.get("matrix_id") if isinstance(item.get("matrix_id"), str) else None
                evidence_block_id = item.get("evidence_block_id") if isinstance(item.get("evidence_block_id"), str) else None
                logic_type = item.get("logic_type") if isinstance(item.get("logic_type"), str) else "Other"
                if not matrix_id:
                    matrix_id = f"mx-{evidence_block_id or uuid4()}"
                standard_matrices.append(
                    {
                        "matrix_id": matrix_id,
                        "inputs": inputs[:20],
                        "outputs": outputs[:20],
                        "logic_type": logic_type,
                        "evidence_ref": block_ref.get(evidence_block_id) if evidence_block_id else None,
                    }
                )

        scopes = obj.get("scope_candidates") if isinstance(obj, dict) else None
        if isinstance(scopes, list):
            for item in scopes:
                if not isinstance(item, dict):
                    continue
                scope_id = item.get("id") if isinstance(item.get("id"), str) else None
                evidence_block_id = item.get("evidence_block_id") if isinstance(item.get("evidence_block_id"), str) else None
                geography_refs = item.get("geography_refs") if isinstance(item.get("geography_refs"), list) else []
                development_types = item.get("development_types") if isinstance(item.get("development_types"), list) else []
                use_classes = item.get("use_classes") if isinstance(item.get("use_classes"), list) else []
                use_class_regime = item.get("use_class_regime") if isinstance(item.get("use_class_regime"), str) else "unknown"
                temporal_scope = item.get("temporal_scope") if isinstance(item.get("temporal_scope"), dict) else {}
                conditions = item.get("conditions") if isinstance(item.get("conditions"), list) else []
                geography_refs = [str(x) for x in geography_refs if isinstance(x, str)]
                development_types = [str(x) for x in development_types if isinstance(x, str)]
                use_classes = [str(x) for x in use_classes if isinstance(x, str)]
                conditions = [str(x) for x in conditions if isinstance(x, str)]
                if not scope_id:
                    scope_id = f"scope-{evidence_block_id or uuid4()}"
                scope_candidates.append(
                    {
                        "id": scope_id,
                        "geography_refs": geography_refs[:20],
                        "development_types": development_types[:20],
                        "use_classes": use_classes[:20],
                        "use_class_regime": use_class_regime,
                        "temporal_scope": temporal_scope,
                        "conditions": conditions[:20],
                        "evidence_ref": block_ref.get(evidence_block_id) if evidence_block_id else None,
                    }
                )

    for block in blocks:
        block_id = block.get("block_id")
        ann = block_annotations.get(block_id) if isinstance(block_id, str) else None
        if not ann:
            continue
        btype = ann.get("block_type")
        if isinstance(btype, str) and btype.strip():
            block["type"] = btype.strip()
        section_path = ann.get("section_path")
        if isinstance(section_path, str) and section_path.strip():
            block["section_path"] = section_path.strip()

    return blocks, policy_headings, standard_matrices, scope_candidates, tool_runs


def _make_evidence_refs(document_id: str, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for block in blocks:
        page_number = int(block.get("page_number") or 0)
        block_id = block.get("block_id") or "block"
        section_ref = f"p{page_number}-{block_id}"
        snippet = str(block.get("text") or "")[:240]
        refs.append(
            {
                "source_doc_id": document_id,
                "section_ref": section_ref,
                "page_number": page_number,
                "snippet_text": snippet,
                "bbox": block.get("bbox"),
                "image_ref": None,
            }
        )
    return refs


def _classify_visuals(
    visuals: list[dict[str, Any]],
    *,
    vlm_model_id: str | None,
    max_visuals: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    classified: list[dict[str, Any]] = []
    tool_runs: list[dict[str, Any]] = []
    prompt = (
        "Classify this visual into one of: map, diagram, photo, render, decorative. "
        "Assign role: governance, context, exemplar. "
        "If exemplar, provide judgment: positive|negative|neutral and a short description. "
        "If diagram-like, extract any quantitative metrics as extracted_metrics: "
        "[{\"label\": \"...\", \"value\": number, \"unit\": \"...\"}]. "
        "Optionally provide constraint_type for diagrams (e.g., BuildingHeight, DaylightAngle). "
        "Optionally provide caption_hint if you can read a caption. "
        "Return JSON only: {"
        "\"asset_type\":..., \"role\":..., \"judgment\":..., \"description\":..., "
        "\"constraint_type\":..., \"extracted_metrics\": [...], \"caption_hint\":...}."
    )
    for idx, item in enumerate(visuals[:max_visuals], start=1):
        data = item.get("bytes")
        if not isinstance(data, (bytes, bytearray)):
            continue
        started = time.time()
        obj, errs = _call_vlm_json(prompt=prompt, image_bytes=bytes(data), model_id=vlm_model_id, time_budget_seconds=120.0)
        elapsed = max(0.0, time.time() - started)
        tool_runs.append(
            {
                "tool_name": "vlm_visual_classification",
                "status": "success" if obj else "error",
                "inputs": {"image_index": idx},
                "outputs": obj or {"errors": errs},
                "duration_seconds": elapsed,
                "limitations_text": "VLM classification is non-deterministic; treat as indicative.",
            }
        )
        classification = obj or {}
        classification["errors"] = errs
        classified.append({**item, "classification": classification})
    return classified, tool_runs


def _call_vectorize(*, image_bytes: bytes, time_budget_seconds: float) -> tuple[list[dict[str, Any]], list[str]]:
    base_url = os.environ.get("TPA_VECTORIZE_BASE_URL")
    if not base_url:
        return [], ["vectorize_unconfigured"]
    timeout = min(max(time_budget_seconds, 2.0), 120.0)
    url = base_url.rstrip("/") + "/vectorize"
    files = {"file": ("image.png", io.BytesIO(image_bytes), "image/png")}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, files=files)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return [], [f"vectorize_failed:{exc}"]
    if isinstance(data, dict) and isinstance(data.get("paths"), list):
        return [p for p in data.get("paths") if isinstance(p, dict)], []
    return [], ["vectorize_invalid_response"]


def _default_role_from_type(asset_type: str) -> str:
    return "context"


def _normalize_asset_type(raw: str) -> str:
    val = (raw or "").strip().lower()
    allowed = {"map", "diagram", "photo", "render", "decorative"}
    if val in allowed:
        return val
    return "decorative"


def _normalize_metrics(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        value = item.get("value")
        unit = item.get("unit")
        if not isinstance(label, str) or not isinstance(unit, str):
            continue
        if not isinstance(value, (int, float)):
            continue
        out.append({"label": label, "value": float(value), "unit": unit})
    return out


@app.post("/parse/bundle")
async def parse_bundle(
    file: UploadFile,
    metadata: str = Form("{}"),
) -> JSONResponse:
    if not file:
        raise HTTPException(status_code=400, detail="file is required")

    content_type = (file.content_type or "").lower()
    if content_type and "pdf" not in content_type:
        raise HTTPException(status_code=400, detail=f"Unsupported content_type: {file.content_type}")

    try:
        meta_obj = json.loads(metadata or "{}")
    except Exception:  # noqa: BLE001
        meta_obj = {}

    authority_id = str(meta_obj.get("authority_id") or "unknown")
    plan_cycle_id = meta_obj.get("plan_cycle_id")
    document_id = str(meta_obj.get("document_id") or uuid4())
    job_id = str(meta_obj.get("job_id") or uuid4())
    source_url = meta_obj.get("source_url") if isinstance(meta_obj.get("source_url"), str) else None

    max_bytes = int(os.environ.get("TPA_DOCPARSE_MAX_BYTES", "50000000"))
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large (>{max_bytes} bytes)")

    reader = PdfReader(io.BytesIO(data))
    max_pages = int(os.environ.get("TPA_DOCPARSE_MAX_PAGES", "800"))
    page_texts = _extract_page_texts(reader, max_pages=max_pages)

    max_visuals = int(os.environ.get("TPA_DOCPARSE_MAX_VISUALS", "120"))
    visuals = _extract_images(reader, max_pages=max_pages, max_visuals=max_visuals)

    blocks = _lines_to_blocks(page_texts)
    for block in blocks:
        block_id = block.get("block_id") or "block"
        page_number = int(block.get("page_number") or 0)
        block["evidence_ref"] = f"doc::{document_id}::p{page_number}-{block_id}"

    evidence_refs = _make_evidence_refs(document_id, blocks)

    llm_model_id = os.environ.get("TPA_LLM_MODEL_ID")
    blocks, policy_headings, standard_matrices, scope_candidates, llm_runs = _annotate_blocks_with_llm(
        blocks,
        llm_model_id=llm_model_id,
    )

    vlm_model_id = os.environ.get("TPA_VLM_MODEL_ID")
    classified_visuals, vlm_runs = _classify_visuals(visuals, vlm_model_id=vlm_model_id, max_visuals=max_visuals)

    vector_paths: list[dict[str, Any]] = []
    vector_tool_runs: list[dict[str, Any]] = []
    for idx, asset in enumerate(classified_visuals, start=1):
        data_bytes = asset.get("bytes")
        if not isinstance(data_bytes, (bytes, bytearray)):
            continue
        asset_type = _normalize_asset_type((asset.get("classification") or {}).get("asset_type"))
        if asset_type in {"map", "diagram"}:
            started = time.time()
            paths, errs = _call_vectorize(image_bytes=bytes(data_bytes), time_budget_seconds=60.0)
            elapsed = max(0.0, time.time() - started)
            for p_idx, path in enumerate(paths, start=1):
                vector_paths.append(
                    {
                        "path_id": f"vp-{idx:04d}-{p_idx:03d}",
                        "page_number": int(asset.get("page_number") or 0),
                        "path_type": asset_type,
                        "geometry": path.get("geometry") if isinstance(path, dict) else None,
                        "bbox": path.get("bbox") if isinstance(path, dict) else None,
                    }
                )
            vector_tool_runs.append(
                {
                    "tool_name": "vectorize_visual_asset",
                    "status": "success" if paths else "error",
                    "inputs": {"image_index": idx, "asset_type": asset_type},
                    "outputs": {"path_count": len(paths), "errors": errs},
                    "duration_seconds": elapsed,
                    "limitations_text": "Vectorization is best-effort; verify geometry and scale.",
                }
            )

    bucket = os.environ.get("TPA_S3_BUCKET") or "tpa"
    minio_client = _minio_client()
    _ensure_bucket(minio_client, bucket)

    asset_items: list[dict[str, Any]] = []
    for idx, asset in enumerate(classified_visuals, start=1):
        data_bytes = asset.get("bytes")
        if not isinstance(data_bytes, (bytes, bytearray)):
            continue
        extension = asset.get("extension") or "png"
        asset_hash = _hash_bytes(bytes(data_bytes))[:16]
        asset_type = _normalize_asset_type((asset.get("classification") or {}).get("asset_type"))
        role = (asset.get("classification") or {}).get("role")
        if not isinstance(role, str):
            role = _default_role_from_type(asset_type)
        classification = asset.get("classification") or {}
        metrics = _normalize_metrics(classification.get("extracted_metrics"))
        caption = classification.get("caption_hint") if isinstance(classification.get("caption_hint"), str) else None
        base_prefix = f"docparse/{authority_id}/{plan_cycle_id or 'none'}/{document_id}"
        blob_path = f"{base_prefix}/visual_assets/{asset_type}/{asset_hash}.{extension}"
        _upload_bytes(
            client=minio_client,
            bucket=bucket,
            blob_path=blob_path,
            data=bytes(data_bytes),
            content_type="image/png",
        )
        asset_items.append(
            {
                "asset_id": f"va-{idx:04d}",
                "page_number": int(asset.get("page_number") or 0),
                "asset_type": asset_type,
                "role": role,
                "blob_path": blob_path,
                "bbox": None,
                "caption": caption,
                "classification": classification,
                "metrics": metrics,
                "width": asset.get("width"),
                "height": asset.get("height"),
            }
        )

    visual_evidence_refs: list[dict[str, Any]] = []
    for asset in asset_items:
        visual_evidence_refs.append(
            {
                "source_doc_id": document_id,
                "section_ref": f"visual::{asset.get('asset_id')}",
                "page_number": int(asset.get("page_number") or 0),
                "snippet_text": None,
                "bbox": asset.get("bbox"),
                "image_ref": asset.get("blob_path"),
            }
        )
    evidence_refs.extend(visual_evidence_refs)

    design_exemplars: list[dict[str, Any]] = []
    visual_constraints: list[dict[str, Any]] = []
    for asset in asset_items:
        classification = asset.get("classification") if isinstance(asset.get("classification"), dict) else {}
        judgment = classification.get("judgment") if isinstance(classification.get("judgment"), str) else None
        description = classification.get("description") if isinstance(classification.get("description"), str) else None
        constraint_type = classification.get("constraint_type") if isinstance(classification.get("constraint_type"), str) else None
        metrics = asset.get("metrics") if isinstance(asset.get("metrics"), list) else []
        evidence_ref = f"visual::{asset.get('asset_id')}"

        if judgment:
            design_exemplars.append(
                {
                    "image_ref": asset.get("blob_path"),
                    "judgment": judgment,
                    "description": description,
                    "evidence_ref": evidence_ref,
                }
            )

        if metrics or constraint_type:
            visual_constraints.append(
                {
                    "type": constraint_type or asset.get("asset_type") or "diagram",
                    "image_ref": asset.get("blob_path"),
                    "extracted_metrics": metrics,
                    "evidence_ref": evidence_ref,
                }
            )

    bundle = {
        "schema_version": "2.0",
        "bundle_id": str(uuid4()),
        "document": {
            "document_id": document_id,
            "authority_id": authority_id,
            "plan_cycle_id": plan_cycle_id,
            "title": file.filename or "Document",
            "source_url": source_url,
            "page_count": len(page_texts),
            "content_bytes": len(data),
        },
        "pages": page_texts,
        "layout_blocks": blocks,
        "tables": [],
        "visual_assets": asset_items,
        "vector_paths": vector_paths,
        "evidence_refs": evidence_refs,
        "semantic": {
            "policy_headings": policy_headings,
            "standard_matrices": standard_matrices,
            "scope_candidates": scope_candidates,
            "visual_constraints": visual_constraints,
            "design_exemplars": design_exemplars,
        },
        "tool_runs": [*llm_runs, *vlm_runs, *vector_tool_runs],
        "limitations": [
            "BBox coordinates are best-effort and may be null for PDF text/images.",
            "Vector extraction is best-effort; map geometry may require follow-up tools.",
        ],
    }

    bundle_path = f"docparse/{authority_id}/{plan_cycle_id or 'none'}/{document_id}/parse_bundles/{job_id}.json"
    _upload_bytes(
        client=minio_client,
        bucket=bucket,
        blob_path=bundle_path,
        data=json.dumps(bundle, ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
    )

    return JSONResponse(
        content={
            "bundle_id": bundle["bundle_id"],
            "parse_bundle_path": bundle_path,
            "asset_count": len(asset_items),
            "page_count": len(page_texts),
            "policy_heading_count": len(policy_headings),
        }
    )


@app.post("/parse/pdf")
async def parse_pdf(file: UploadFile) -> JSONResponse:
    if not file:
        raise HTTPException(status_code=400, detail="file is required")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    reader = PdfReader(io.BytesIO(data))
    page_texts = _extract_page_texts(reader, max_pages=200)
    blocks = _lines_to_blocks(page_texts)
    return JSONResponse(
        content={
            "provider": "docparse_v2",
            "pages": page_texts,
            "chunks": blocks,
        }
    )
