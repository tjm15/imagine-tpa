from __future__ import annotations

import re
from typing import Any


def _semantic_chunk_lines(
    *,
    lines: list[str],
    section_stack: list[str],
    max_chunk_chars: int = 1800,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Heuristic, planner-shaped chunking:
    - keep headings as their own chunks,
    - group bullet runs,
    - split paragraphs on blank lines,
    - maintain a simple `section_stack` to form `section_path`.

    This is a pragmatic stopgap until Docling-driven structure is available everywhere.
    """

    def is_heading(line: str) -> bool:
        s = line.strip()
        if not s:
            return False
        if len(s) > 120:
            return False
        if re.match(r"^(chapter|policy|appendix|part|section)\b", s, flags=re.IGNORECASE):
            return True
        if s.endswith(":") and len(s) <= 80:
            return True
        upper = sum(1 for ch in s if ch.isupper())
        letters = sum(1 for ch in s if ch.isalpha())
        if letters >= 8 and upper / max(letters, 1) >= 0.8 and len(s) <= 80:
            return True
        return False

    def is_bullet(line: str) -> bool:
        s = line.lstrip()
        return bool(re.match(r"^([-•*]\s+|\d+\.\s+|[A-Za-z]\)\s+)", s))

    chunks: list[dict[str, Any]] = []
    paragraph: list[str] = []
    bullets: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        text = "\n".join(paragraph).strip()
        paragraph = []
        if not text:
            return
        chunks.append({"type": "paragraph", "text": text})

    def flush_bullets() -> None:
        nonlocal bullets
        text = "\n".join(bullets).strip()
        bullets = []
        if not text:
            return
        chunks.append({"type": "bullets", "text": text})

    for raw in lines:
        line = raw.strip()
        if not line:
            flush_bullets()
            flush_paragraph()
            continue

        if is_heading(line):
            flush_bullets()
            flush_paragraph()
            section_stack = [line[:160]]
            chunks.append({"type": "heading", "text": line})
            continue

        if is_bullet(line):
            flush_paragraph()
            bullets.append(line)
            continue

        flush_bullets()
        paragraph.append(line)

    flush_bullets()
    flush_paragraph()

    # enforce max chunk size (split long chunks conservatively)
    out: list[dict[str, Any]] = []
    section_path = " > ".join([s for s in section_stack if s])
    for c in chunks:
        text = c["text"]
        ctype = c["type"]
        if len(text) <= max_chunk_chars:
            out.append({"type": ctype, "text": text, "section_path": section_path or None})
            continue
        # split by sentences-ish
        parts = re.split(r"(?<=[\.\!\?])\s+", text)
        buf = ""
        for p in parts:
            if not p:
                continue
            if len(buf) + len(p) + 1 > max_chunk_chars and buf.strip():
                out.append({"type": ctype, "text": buf.strip(), "section_path": section_path or None})
                buf = p
            else:
                buf = (buf + " " + p).strip()
        if buf.strip():
            out.append({"type": ctype, "text": buf.strip(), "section_path": section_path or None})

    return out, section_stack

