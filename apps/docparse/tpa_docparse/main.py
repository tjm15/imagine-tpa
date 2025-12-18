from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import JSONResponse


app = FastAPI(title="TPA DocParse (Docling)", version="0.0.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _markdown_to_chunks(markdown: str, *, max_chunk_chars: int = 1800) -> list[dict[str, Any]]:
    """
    Best-effort structural chunking of Docling markdown output.

    This is a retrieval/sectioning aid (not a decision engine). It preserves headings, bullet runs and paragraph
    runs where possible. Page numbers and bounding boxes are not guaranteed because Docling output varies by
    version/config.
    """

    def is_md_heading(line: str) -> bool:
        return bool(re.match(r"^\\s{0,3}#{1,6}\\s+\\S", line))

    def normalize_heading(line: str) -> str:
        return re.sub(r"^\\s{0,3}#{1,6}\\s+", "", line).strip()

    def is_bullet(line: str) -> bool:
        return bool(re.match(r"^\\s*([-*+]\\s+|\\d+\\.\\s+)", line))

    section_stack: list[str] = []
    chunks: list[dict[str, Any]] = []
    paragraph: list[str] = []
    bullets: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        text = "\n".join(paragraph).strip()
        paragraph = []
        if not text:
            return
        chunks.append({"type": "paragraph", "text": text, "section_path": " > ".join(section_stack) or None})

    def flush_bullets() -> None:
        nonlocal bullets
        text = "\n".join(bullets).strip()
        bullets = []
        if not text:
            return
        chunks.append({"type": "bullets", "text": text, "section_path": " > ".join(section_stack) or None})

    for raw in (markdown or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush_bullets()
            flush_paragraph()
            continue

        if is_md_heading(line):
            flush_bullets()
            flush_paragraph()
            heading = normalize_heading(line)[:160]
            if heading:
                section_stack = [heading]
                chunks.append({"type": "heading", "text": heading, "section_path": " > ".join(section_stack)})
            continue

        if is_bullet(line):
            flush_paragraph()
            bullets.append(line.strip())
            continue

        flush_bullets()
        paragraph.append(line.strip())

    flush_bullets()
    flush_paragraph()

    # split oversized chunks conservatively
    out: list[dict[str, Any]] = []
    for ch in chunks:
        text = str(ch.get("text") or "")
        if len(text) <= max_chunk_chars:
            out.append(ch)
            continue
        parts = re.split(r"(?<=[\\.\\!\\?])\\s+", text)
        buf = ""
        for p in parts:
            if not p:
                continue
            if len(buf) + len(p) + 1 > max_chunk_chars and buf.strip():
                out.append({**ch, "text": buf.strip()})
                buf = p
            else:
                buf = (buf + " " + p).strip()
        if buf.strip():
            out.append({**ch, "text": buf.strip()})

    return out


@app.post("/parse/pdf")
async def parse_pdf(file: UploadFile) -> JSONResponse:
    if not file:
        raise HTTPException(status_code=400, detail="file is required")

    content_type = (file.content_type or "").lower()
    if content_type and "pdf" not in content_type:
        raise HTTPException(status_code=400, detail=f"Unsupported content_type: {file.content_type}")

    try:
        from docling.document_converter import DocumentConverter  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Docling import failed: {exc}") from exc

    max_bytes = int(os.environ.get("TPA_DOCPARSE_MAX_BYTES", "50000000"))
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large (>{max_bytes} bytes)")

    tmpdir = Path(tempfile.mkdtemp(prefix="tpa-docparse-"))
    try:
        pdf_path = tmpdir / (file.filename or "document.pdf")
        pdf_path.write_bytes(data)

        converter = DocumentConverter()
        result = converter.convert(str(pdf_path))
        doc = getattr(result, "document", result)
        pages = getattr(doc, "pages", None)

        page_items: list[dict[str, Any]] = []
        page_texts: list[str] = []
        if isinstance(pages, list):
            for i, p in enumerate(pages, start=1):
                text = getattr(p, "text", None) or getattr(p, "text_content", None) or ""
                if not isinstance(text, str):
                    text = ""
                page_items.append({"page_number": i, "text": text})
                page_texts.append(text)

        markdown: str | None = None
        for attr in ("export_to_markdown", "to_markdown", "as_markdown"):
            try:
                fn = getattr(doc, attr, None)
                if callable(fn):
                    out = fn()
                    if isinstance(out, str) and out.strip():
                        markdown = out
                        break
            except Exception:  # noqa: BLE001
                continue

        chunks: list[dict[str, Any]] = []
        if markdown:
            chunks = _markdown_to_chunks(markdown)

        return JSONResponse(
            content={
                "provider": "docling",
                "pages": page_items,
                "page_texts": page_texts,
                "markdown": markdown,
                "chunks": chunks,
                "tables": [],
            }
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Docling parse failed: {exc}") from exc
    finally:
        try:
            for p in tmpdir.glob("**/*"):
                try:
                    p.unlink()
                except Exception:  # noqa: BLE001
                    pass
            try:
                tmpdir.rmdir()
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass
