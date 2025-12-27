from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import tempfile
import time
from typing import Any
from uuid import uuid4
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse

from pdf2image import convert_from_bytes
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


def _call_llm_json(*, prompt: str, model_id: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    base_url = os.environ.get("TPA_LLM_BASE_URL")
    if not base_url:
        return None, ["llm_unconfigured"]
    model = model_id or os.environ.get("TPA_LLM_MODEL_ID") or "openai/gpt-oss-20b"
    timeout = None
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
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


def _call_vlm_json(*, prompt: str, image_bytes: bytes, model_id: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    base_url = os.environ.get("TPA_VLM_BASE_URL")
    if not base_url:
        return None, ["vlm_unconfigured"]
    model = model_id or os.environ.get("TPA_VLM_MODEL_ID") or "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8"
    timeout = None
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


def _get_attr(obj: Any, *names: str) -> Any:
    if isinstance(obj, dict):
        for name in names:
            if name in obj:
                return obj.get(name)
        return None
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _normalize_bbox(raw: Any) -> tuple[list[float] | None, str]:
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            return [float(x) for x in raw], "exact"
        except Exception:  # noqa: BLE001
            return None, "none"
    if isinstance(raw, dict):
        keys = raw.keys()
        if {"x0", "y0", "x1", "y1"} <= set(keys):
            try:
                return [float(raw["x0"]), float(raw["y0"]), float(raw["x1"]), float(raw["y1"])], "exact"
            except Exception:  # noqa: BLE001
                return None, "none"
        if {"left", "top", "right", "bottom"} <= set(keys):
            try:
                return [float(raw["left"]), float(raw["top"]), float(raw["right"]), float(raw["bottom"])], "exact"
            except Exception:  # noqa: BLE001
                return None, "none"
        if {"x", "y", "width", "height"} <= set(keys):
            try:
                x0 = float(raw["x"])
                y0 = float(raw["y"])
                return [x0, y0, x0 + float(raw["width"]), y0 + float(raw["height"])], "approx"
            except Exception:  # noqa: BLE001
                return None, "none"
    return None, "none"


def _docling_to_dict(doc: Any) -> dict[str, Any] | None:
    for attr in ("model_dump", "to_dict", "dict"):
        if hasattr(doc, attr):
            try:
                data = getattr(doc, attr)()
            except Exception:  # noqa: BLE001
                continue
            if isinstance(data, dict):
                return data
    if isinstance(doc, dict):
        return doc
    return None


def _extract_docling_tables(raw: Any) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return tables
    for idx, table in enumerate(raw, start=1):
        if not isinstance(table, dict):
            table_dict = _docling_to_dict(table)
        else:
            table_dict = table
        if not isinstance(table_dict, dict):
            continue
        rows = table_dict.get("rows")
        if not isinstance(rows, list):
            rows = table_dict.get("cells")
        if not isinstance(rows, list):
            continue
        page_number = table_dict.get("page_number") or table_dict.get("page") or 0
        bbox_raw = table_dict.get("bbox") or table_dict.get("bounding_box")
        bbox, bbox_quality = _normalize_bbox(bbox_raw)
        tables.append(
            {
                "table_id": table_dict.get("table_id") or f"t-{idx:04d}",
                "page_number": int(page_number) if page_number else 0,
                "bbox": bbox,
                "bbox_quality": bbox_quality,
                "rows": rows,
            }
        )
    return tables


def _extract_docling_blocks(page: Any, page_number: int) -> list[dict[str, Any]]:
    blocks_raw = _get_attr(page, "blocks", "layout_blocks", "elements", "regions")
    if not isinstance(blocks_raw, list):
        return []
    blocks: list[dict[str, Any]] = []
    for idx, block in enumerate(blocks_raw, start=1):
        block_dict = block if isinstance(block, dict) else _docling_to_dict(block)
        if not isinstance(block_dict, dict):
            continue
        text = block_dict.get("text") or block_dict.get("content") or ""
        block_type = block_dict.get("type") or block_dict.get("block_type") or block_dict.get("label") or "other"
        bbox_raw = block_dict.get("bbox") or block_dict.get("bounding_box") or block_dict.get("box")
        bbox, bbox_quality = _normalize_bbox(bbox_raw)
        blocks.append(
            {
                "block_id": block_dict.get("block_id") or f"b-{page_number:03d}-{idx:04d}",
                "type": str(block_type),
                "text": str(text),
                "page_number": page_number,
                "section_path": block_dict.get("section_path"),
                "bbox": bbox,
                "bbox_quality": bbox_quality,
            }
        )
    return blocks


def _select_render_tier(
    *,
    page_text: str,
    visual_count: int,
    docling_used: bool,
    docling_errors: list[str],
) -> tuple[str, str]:
    del page_text, visual_count, docling_used, docling_errors
    return "full", "full_res_only"


def _render_page_images(
    *,
    pdf_bytes: bytes,
    pages: list[dict[str, Any]],
    visuals_by_page: dict[int, int],
    authority_id: str,
    plan_cycle_id: str | None,
    document_id: str,
    docling_used: bool,
    docling_errors: list[str],
    minio_client: Minio,
    bucket: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    render_dpi = 300
    fmt = "png"
    ext = "png"

    render_runs: list[dict[str, Any]] = []
    rendered_pages: list[dict[str, Any]] = []
    for page in pages:
        page_number = int(page.get("page_number") or 0)
        if page_number <= 0:
            continue
        page_text = page.get("text") if isinstance(page.get("text"), str) else ""
        visual_count = int(visuals_by_page.get(page_number, 0))
        tier, reason = _select_render_tier(
            page_text=page_text,
            visual_count=visual_count,
            docling_used=docling_used,
            docling_errors=docling_errors,
        )
        dpi = render_dpi

        started = time.time()
        try:
            images = convert_from_bytes(
                pdf_bytes,
                dpi=dpi,
                first_page=page_number,
                last_page=page_number,
                fmt=fmt,
            )
        except Exception as exc:  # noqa: BLE001
            render_runs.append(
                {
                    "tool_name": "page_render",
                    "status": "error",
                    "inputs": {"page_number": page_number, "dpi": dpi, "format": fmt},
                    "outputs": {"error": str(exc)},
                    "duration_seconds": max(0.0, time.time() - started),
                    "limitations_text": "Page render failed; raster output required for explainability layers.",
                }
            )
            raise HTTPException(status_code=500, detail=f"page_render_failed:p{page_number}:{exc}") from exc
        if not images:
            render_runs.append(
                {
                    "tool_name": "page_render",
                    "status": "error",
                    "inputs": {"page_number": page_number, "dpi": dpi, "format": fmt},
                    "outputs": {"error": "no_images_returned"},
                    "duration_seconds": max(0.0, time.time() - started),
                    "limitations_text": "No raster output returned for the requested page.",
                }
            )
            raise HTTPException(status_code=500, detail=f"page_render_failed:p{page_number}:no_output")

        img = images[0]
        out = io.BytesIO()
        img.save(out, format="PNG")
        img_bytes = out.getvalue()

        base_prefix = f"docparse/{authority_id}/{plan_cycle_id or 'none'}/{document_id}"
        blob_path = f"{base_prefix}/page_renders/p{page_number:04d}-{tier.lower()}.{ext}"
        _upload_bytes(
            client=minio_client,
            bucket=bucket,
            blob_path=blob_path,
            data=img_bytes,
            content_type="image/png",
        )

        rendered_pages.append(
            {
                "page_number": page_number,
                "render_blob_path": blob_path,
                "render_format": fmt,
                "render_dpi": dpi,
                "render_width": img.width,
                "render_height": img.height,
                "render_tier": tier,
                "render_reason": reason,
            }
        )
        render_runs.append(
            {
                "tool_name": "page_render",
                "status": "success",
                "inputs": {"page_number": page_number, "dpi": dpi, "format": fmt, "tier": tier},
                "outputs": {"render_path": blob_path, "width": img.width, "height": img.height},
                "duration_seconds": max(0.0, time.time() - started),
                "limitations_text": "Raster page renders are for explainability overlays; verify scale before measurements.",
            }
        )

    return rendered_pages, render_runs


def _docling_parse_pdf(
    *,
    file_bytes: bytes,
    filename: str,
    max_pages: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    try:
        from docling.document_converter import DocumentConverter  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        return [], [], [], [], [f"docling_unavailable:{exc}"]

    temp_path = None
    pages: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    tool_runs: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1] or ".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            temp_path = tmp.name

        converter = DocumentConverter()
        result = converter.convert(temp_path)
        doc = getattr(result, "document", result)
        data = _docling_to_dict(doc)

        if isinstance(data, dict):
            pages_raw = data.get("pages")
            if isinstance(pages_raw, list):
                for idx, page in enumerate(pages_raw, start=1):
                    if max_pages is not None and idx > max_pages:
                        break
                    page_number = page.get("page_number") or page.get("page") or idx
                    text = page.get("text") or page.get("content") or ""
                    page_item: dict[str, Any] = {"page_number": int(page_number), "text": str(text)}
                    for key in ("width", "height"):
                        if key in page:
                            page_item[key] = page.get(key)
                    pages.append(page_item)
                    blocks.extend(_extract_docling_blocks(page, int(page_number)))
                    tables.extend(_extract_docling_tables(page.get("tables")))
            tables.extend(_extract_docling_tables(data.get("tables")))

        if not pages:
            pages_raw = _get_attr(doc, "pages")
            if isinstance(pages_raw, list):
                for idx, page in enumerate(pages_raw, start=1):
                    if max_pages is not None and idx > max_pages:
                        break
                    text = _get_attr(page, "text", "text_content", "content") or ""
                    page_number = _get_attr(page, "page_number", "page", "number") or idx
                    pages.append({"page_number": int(page_number), "text": str(text)})
                    blocks.extend(_extract_docling_blocks(page, int(page_number)))

        tool_runs.append(
            {
                "tool_name": "docling_parse",
                "status": "success" if pages else "partial",
                "inputs": {"filename": filename, "max_pages": max_pages},
                "outputs": {"page_count": len(pages), "block_count": len(blocks), "table_count": len(tables)},
                "duration_seconds": None,
                "limitations_text": "Docling output is deterministic but may miss layout elements in complex PDFs.",
            }
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"docling_failed:{exc}")
        tool_runs.append(
            {
                "tool_name": "docling_parse",
                "status": "error",
                "inputs": {"filename": filename, "max_pages": max_pages},
                "outputs": {"error": str(exc)},
                "duration_seconds": None,
                "limitations_text": "Docling parsing failed; fallback extraction used.",
            }
        )
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except Exception:  # noqa: BLE001
                pass

    return pages, blocks, tables, tool_runs, errors


def _extract_page_texts(reader: PdfReader, *, max_pages: int | None) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for idx, page in enumerate(reader.pages, start=1):
        if max_pages is not None and idx > max_pages:
            break
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        pages.append({"page_number": idx, "text": text})
    return pages


def _choose_page_text_source(
    *,
    docling_page: dict[str, Any] | None,
    fallback_page: dict[str, Any] | None,
    docling_errors: list[str],
) -> tuple[dict[str, Any] | None, str, str]:
    if not docling_page and not fallback_page:
        return None, "unknown", "no_pages"
    if not docling_page:
        return fallback_page, "pypdf", "docling_missing"
    if not fallback_page:
        return docling_page, "docling", "fallback_missing"

    doc_text = str(docling_page.get("text") or "").strip()
    fallback_text = str(fallback_page.get("text") or "").strip()
    doc_len = len(doc_text)
    fallback_len = len(fallback_text)

    if doc_len == 0 and fallback_len == 0:
        return fallback_page, "pypdf", "both_empty"
    if doc_len == 0:
        return fallback_page, "pypdf", "docling_empty"
    if fallback_len == 0:
        return docling_page, "docling", "fallback_empty"

    ratio = doc_len / max(1, fallback_len)
    if docling_errors and ratio < 0.9:
        return fallback_page, "pypdf", f"docling_errors_ratio_{ratio:.2f}"
    if ratio >= 0.6:
        return docling_page, "docling", f"ratio_{ratio:.2f}"
    return fallback_page, "pypdf", f"ratio_{ratio:.2f}"


def _merge_page_texts(
    *,
    docling_pages: list[dict[str, Any]],
    fallback_pages: list[dict[str, Any]],
    docling_errors: list[str],
) -> tuple[list[dict[str, Any]], dict[int, str]]:
    merged: list[dict[str, Any]] = []
    sources: dict[int, str] = {}
    docling_by_page = {int(p.get("page_number") or 0): p for p in docling_pages if p.get("page_number")}
    fallback_by_page = {int(p.get("page_number") or 0): p for p in fallback_pages if p.get("page_number")}
    page_numbers = sorted({*docling_by_page.keys(), *fallback_by_page.keys()})

    for page_number in page_numbers:
        docling_page = docling_by_page.get(page_number)
        fallback_page = fallback_by_page.get(page_number)
        chosen, source, reason = _choose_page_text_source(
            docling_page=docling_page,
            fallback_page=fallback_page,
            docling_errors=docling_errors,
        )
        if not chosen:
            continue
        page_item = dict(chosen)
        page_item["page_number"] = page_number
        page_item["text_source"] = source
        page_item["text_source_reason"] = reason
        merged.append(page_item)
        sources[page_number] = source

    return merged, sources


def _extract_images(reader: PdfReader, *, max_pages: int | None, max_visuals: int | None) -> list[dict[str, Any]]:
    visuals: list[dict[str, Any]] = []
    for idx, page in enumerate(reader.pages, start=1):
        if max_pages is not None and idx > max_pages:
            break
        if not getattr(page, "images", None):
            continue
        for image in page.images:
            if max_visuals is not None and len(visuals) >= max_visuals:
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
                            "bbox_quality": "none",
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
                    "bbox_quality": "none",
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


def _normalize_block_ids(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counters: dict[int, int] = {}
    for block in blocks:
        page_number = int(block.get("page_number") or 0)
        counters[page_number] = counters.get(page_number, 0) + 1
        new_id = f"blk-{page_number:04d}-{counters[page_number]:04d}"
        meta = dict(block.get("metadata") or {})
        meta.setdefault("source_block_id", block.get("block_id"))
        meta.setdefault("block_id_scheme", "tpa_norm_v1")
        block["metadata"] = meta
        block["block_id"] = new_id
    return blocks


def _annotate_blocks_with_llm(
    blocks: list[dict[str, Any]],
    *,
    llm_model_id: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not blocks:
        return blocks, [], [], [], []
    if not llm_model_id or os.environ.get("TPA_DOCPARSE_DISABLE_LLM", "").lower() == "true":
        return (
            blocks,
            [],
            [],
            [],
            [
                {
                    "tool_name": "llm_block_annotation",
                    "status": "skipped",
                    "inputs": {"reason": "llm_disabled"},
                    "outputs": {},
                    "duration_seconds": 0.0,
                    "limitations_text": "LLM annotation disabled; DocParse emits layout-only bundles.",
                }
            ],
        )

    max_blocks = int(os.environ.get("TPA_DOC_PARSE_LLM_BLOCKS_PER_PASS", "120"))
    max_chars = int(os.environ.get("TPA_DOC_PARSE_LLM_CHARS_PER_PASS", "60000"))
    groups = _chunk_blocks_for_llm(blocks, max_blocks=max_blocks, max_chars=max_chars)
    if not groups:
        groups = [blocks]

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


async def _classify_visuals(
    visuals: list[dict[str, Any]],
    *,
    vlm_model_id: str | None,
    max_visuals: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    classified: list[dict[str, Any]] = []
    tool_runs: list[dict[str, Any]] = []
    prompt = (
        "Classify this visual into one of: map, diagram, photo, render, decorative. "
        "Assign role: governance, context, exemplar. "
        "If diagram-like, extract any quantitative metrics as extracted_metrics: "
        "[{\"label\": \"...\", \"value\": number, \"unit\": \"...\"}]. "
        "Optionally provide constraint_type for diagrams (e.g., BuildingHeight, DaylightAngle). "
        "Optionally provide caption_hint if you can read a caption. "
        "Return JSON only: {"
        "\"asset_type\":..., \"role\":..., "
        "\"constraint_type\":..., \"extracted_metrics\": [...], \"caption_hint\":...}."
    )
    iterable = visuals if max_visuals is None else visuals[:max_visuals]
    concurrency = int(os.environ.get("TPA_VLM_CONCURRENCY", "4"))
    semaphore = asyncio.Semaphore(concurrency if concurrency > 0 else 1)

    async def _classify_one(idx: int, item: dict[str, Any]) -> tuple[int, dict[str, Any], dict[str, Any]] | None:
        data = item.get("bytes")
        if not isinstance(data, (bytes, bytearray)):
            return None
        async with semaphore:
            started = time.time()
            obj, errs = await asyncio.to_thread(
                _call_vlm_json,
                prompt=prompt,
                image_bytes=bytes(data),
                model_id=vlm_model_id,
            )
            elapsed = max(0.0, time.time() - started)
        classification = obj or {}
        classification["errors"] = errs
        tool_run = {
            "tool_name": "vlm_visual_classification",
            "status": "success" if obj else "error",
            "inputs": {"image_index": idx},
            "outputs": obj or {"errors": errs},
            "duration_seconds": elapsed,
            "limitations_text": "VLM classification is non-deterministic; treat as indicative.",
        }
        return idx, {**item, "classification": classification}, tool_run

    tasks = [asyncio.create_task(_classify_one(idx, item)) for idx, item in enumerate(iterable, start=1)]
    results: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    for task in asyncio.as_completed(tasks):
        res = await task
        if not res:
            continue
        idx, classified_item, tool_run = res
        results[idx] = (classified_item, tool_run)

    for idx in sorted(results.keys()):
        classified_item, tool_run = results[idx]
        classified.append(classified_item)
        tool_runs.append(tool_run)
    return classified, tool_runs


def _default_role_from_type(asset_type: str) -> str:
    return "context"


def _normalize_asset_type(raw: str) -> str:
    val = (raw or "").strip().lower()
    if not val:
        return "unknown"
    allowed = {"map", "diagram", "photo", "render", "decorative", "unknown"}
    if val in allowed:
        return val
    return "unknown"


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

    data = await file.read()

    reader = PdfReader(io.BytesIO(data))

    docling_pages, docling_blocks, docling_tables, docling_runs, docling_errors = _docling_parse_pdf(
        file_bytes=data,
        filename=file.filename or "document.pdf",
        max_pages=None,
    )

    fallback_pages = _extract_page_texts(reader, max_pages=None)
    page_texts, page_sources = _merge_page_texts(
        docling_pages=docling_pages,
        fallback_pages=fallback_pages,
        docling_errors=docling_errors,
    )
    docling_used = any(source == "docling" for source in page_sources.values()) or bool(docling_blocks)

    visuals = _extract_images(reader, max_pages=None, max_visuals=None)
    visuals_by_page: dict[int, int] = {}
    for asset in visuals:
        page_number = int(asset.get("page_number") or 0)
        if page_number <= 0:
            continue
        visuals_by_page[page_number] = visuals_by_page.get(page_number, 0) + 1

    page_source_reason = {
        int(p.get("page_number") or 0): p.get("text_source_reason") for p in page_texts if p.get("page_number")
    }
    docling_blocks_by_page: dict[int, list[dict[str, Any]]] = {}
    for block in docling_blocks:
        page_number = int(block.get("page_number") or 0)
        if page_number <= 0:
            continue
        docling_blocks_by_page.setdefault(page_number, []).append(block)

    docling_blocks_filtered: list[dict[str, Any]] = []
    for page_number, items in docling_blocks_by_page.items():
        if page_sources.get(page_number) != "docling":
            continue
        for block in items:
            block_meta = dict(block.get("metadata") or {})
            block_meta.setdefault("text_source", "docling")
            block_meta.setdefault("text_source_reason", page_source_reason.get(page_number))
            block["metadata"] = block_meta
            docling_blocks_filtered.append(block)

    fallback_pages_for_blocks = [
        p
        for p in fallback_pages
        if page_sources.get(int(p.get("page_number") or 0)) != "docling"
        or int(p.get("page_number") or 0) not in docling_blocks_by_page
    ]
    fallback_blocks = _lines_to_blocks(fallback_pages_for_blocks)
    for block in fallback_blocks:
        block_meta = dict(block.get("metadata") or {})
        block_meta.setdefault("text_source", "pypdf")
        block_meta.setdefault("text_source_reason", page_source_reason.get(int(block.get("page_number") or 0)))
        block["metadata"] = block_meta

    blocks = [*docling_blocks_filtered, *fallback_blocks]
    blocks = _normalize_block_ids(blocks)
    tables = docling_tables
    tables_unimplemented = (not docling_used) or bool(docling_errors)
    parse_flags: list[str] = []
    if not docling_used:
        parse_flags.append("docling_fallback")
    elif any(source == "pypdf" for source in page_sources.values()):
        parse_flags.append("docling_hybrid_merge")
    if docling_errors:
        parse_flags.append("docling_errors")
    if tables_unimplemented:
        parse_flags.append("tables_unimplemented")
    for block in blocks:
        block_id = block.get("block_id") or "block"
        page_number = int(block.get("page_number") or 0)
        block["evidence_ref"] = f"doc::{document_id}::p{page_number}-{block_id}"

    evidence_refs = _make_evidence_refs(document_id, blocks)
    llm_model_id = os.environ.get("TPA_LLM_MODEL_ID")
    (
        blocks,
        policy_headings,
        standard_matrices,
        scope_candidates,
        llm_runs,
    ) = _annotate_blocks_with_llm(blocks, llm_model_id=llm_model_id)

    bucket = os.environ.get("TPA_S3_BUCKET") or "tpa"
    minio_client = _minio_client()
    _ensure_bucket(minio_client, bucket)

    rendered_pages, render_tool_runs = _render_page_images(
        pdf_bytes=data,
        pages=page_texts,
        visuals_by_page=visuals_by_page,
        authority_id=authority_id,
        plan_cycle_id=plan_cycle_id,
        document_id=document_id,
        docling_used=docling_used,
        docling_errors=docling_errors,
        minio_client=minio_client,
        bucket=bucket,
    )
    render_by_page = {p["page_number"]: p for p in rendered_pages}
    for page in page_texts:
        page_number = int(page.get("page_number") or 0)
        render = render_by_page.get(page_number)
        if render:
            page.update(render)

    vlm_model_id = os.environ.get("TPA_VLM_MODEL_ID")
    vlm_base_url = os.environ.get("TPA_VLM_BASE_URL")
    vlm_enabled = bool(vlm_model_id and vlm_model_id.strip() and vlm_base_url and vlm_base_url.strip())
    if vlm_enabled:
        classified_visuals, vlm_runs = await _classify_visuals(visuals, vlm_model_id=vlm_model_id, max_visuals=None)
    else:
        parse_flags.append("vlm_disabled")
        classified_visuals = []
        for asset in visuals:
            asset_copy = dict(asset)
            asset_copy["classification"] = {"status": "skipped", "reason": "vlm_disabled"}
            classified_visuals.append(asset_copy)
        vlm_runs = [
            {
                "tool_name": "vlm_visual_classification",
                "status": "skipped",
                "inputs": {"image_count": len(visuals)},
                "outputs": {"reason": "vlm_disabled"},
                "duration_seconds": None,
                "limitations_text": "VLM classification disabled in DocParse; deferred to ingest pipeline.",
            }
        ]

    vector_paths: list[dict[str, Any]] = []
    vector_tool_runs: list[dict[str, Any]] = []
    if classified_visuals:
        vector_tool_runs.append(
            {
                "tool_name": "vectorize_visual_asset",
                "status": "skipped",
                "inputs": {"image_count": len(classified_visuals)},
                "outputs": {"reason": "deferred_to_ingestion_pipeline"},
                "duration_seconds": None,
                "limitations_text": "Vectorization deferred to ingestion pipeline (post-segmentation).",
            }
        )

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

    visual_constraints: list[dict[str, Any]] = []
    for asset in asset_items:
        classification = asset.get("classification") if isinstance(asset.get("classification"), dict) else {}
        constraint_type = classification.get("constraint_type") if isinstance(classification.get("constraint_type"), str) else None
        metrics = asset.get("metrics") if isinstance(asset.get("metrics"), list) else []
        evidence_ref = f"visual::{asset.get('asset_id')}"

        if metrics or constraint_type:
            visual_constraints.append(
                {
                    "type": constraint_type or asset.get("asset_type") or "diagram",
                    "image_ref": asset.get("blob_path"),
                    "extracted_metrics": metrics,
                    "evidence_ref": evidence_ref,
                }
            )

    limitations: list[str] = [
        "BBox coordinates are best-effort and may be null for PDF text/images.",
        "Vector extraction is best-effort; map geometry may require follow-up tools.",
    ]
    if docling_errors:
        limitations.append("Docling reported errors; affected pages may rely on fallback text.")

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
        "tables": tables,
        "visual_assets": asset_items,
        "vector_paths": vector_paths,
        "evidence_refs": evidence_refs,
        "docling_errors": docling_errors,
        "semantic": {
            "policy_headings": policy_headings,
            "standard_matrices": standard_matrices,
            "scope_candidates": scope_candidates,
            "visual_constraints": visual_constraints,
        },
        "tool_runs": [*docling_runs, *render_tool_runs, *llm_runs, *vlm_runs, *vector_tool_runs],
        "limitations": limitations,
        "tables_unimplemented": tables_unimplemented,
        "parse_flags": parse_flags,
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
            "docling_errors": docling_errors,
            "parse_flags": parse_flags,
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
    docling_pages, docling_blocks, _, _, docling_errors = _docling_parse_pdf(
        file_bytes=data,
        filename=file.filename or "document.pdf",
        max_pages=None,
    )
    if docling_pages:
        page_texts = docling_pages
    else:
        page_texts = _extract_page_texts(reader, max_pages=None)
    blocks = docling_blocks if docling_blocks else _lines_to_blocks(page_texts)
    provider = "docling" if docling_pages and not docling_errors else "pypdf"
    return JSONResponse(
        content={
            "provider": provider,
            "pages": page_texts,
            "chunks": blocks,
        }
    )
