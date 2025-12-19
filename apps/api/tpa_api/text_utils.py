from __future__ import annotations

import json
import re
from typing import Any


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """
    Best-effort extraction of a single JSON object from an LLM response.
    """
    if not text:
        return None
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None

