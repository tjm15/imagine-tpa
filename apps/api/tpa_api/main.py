from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from datetime import datetime, timezone

import yaml
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse


def _spec_root() -> Path:
    return Path(os.environ.get("TPA_SPEC_ROOT", "/app/spec")).resolve()


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {path}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read YAML: {path}") from exc


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {path}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read JSON: {path}") from exc


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


app = FastAPI(title="TPA API (Scaffold)", version="0.0.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/spec/culp/process-model")
def culp_process_model() -> JSONResponse:
    root = _spec_root()
    model_path = root / "culp" / "PROCESS_MODEL.yaml"
    return JSONResponse(content=_read_yaml(model_path))


@app.get("/spec/culp/artefact-registry")
def culp_artefact_registry() -> JSONResponse:
    root = _spec_root()
    registry_path = root / "culp" / "ARTEFACT_REGISTRY.yaml"
    return JSONResponse(content=_read_yaml(registry_path))


@app.get("/spec/authorities/selected")
def selected_authorities() -> JSONResponse:
    root = _spec_root()
    selected_path = root / "authorities" / "SELECTED_AUTHORITIES.yaml"
    return JSONResponse(content=_read_yaml(selected_path))


@app.get("/spec/framing/political-framings")
def political_framings() -> JSONResponse:
    root = _spec_root()
    framings_path = root / "framing" / "POLITICAL_FRAMINGS.yaml"
    return JSONResponse(content=_read_yaml(framings_path))


async def _llm_blocks(
    *,
    draft_request: dict[str, Any],
    time_budget_seconds: float,
) -> list[dict[str, Any]] | None:
    base_url = os.environ.get("TPA_LLM_BASE_URL")
    if not base_url:
        return None

    model = os.environ.get("TPA_LLM_MODEL", "openai/gpt-oss-20b")
    timeout = min(max(time_budget_seconds, 1.0), 60.0)

    system = (
        "You are The Planner's Assistant. Produce a quick first draft for a UK planning professional. "
        "Return ONLY valid JSON with this shape: "
        "{ \"blocks\": [ {\"block_type\": \"heading|paragraph|bullets|callout|other\", \"content\": string, "
        "\"requires_judgement_run\": boolean } ] }. "
        "Keep it concise and useful. Do not include markdown fences."
    )
    user = json.dumps(draft_request, ensure_ascii=False)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.7,
        "max_tokens": 900,
    }

    url = base_url.rstrip("/") + "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return None

    obj = _extract_json_object(content)
    if not obj:
        return None
    blocks = obj.get("blocks")
    if not isinstance(blocks, list):
        return None
    cleaned: list[dict[str, Any]] = []
    for b in blocks[:8]:
        if not isinstance(b, dict):
            continue
        block_type = b.get("block_type")
        content_text = b.get("content")
        requires = b.get("requires_judgement_run")
        if block_type not in {"heading", "paragraph", "bullets", "callout", "other"}:
            continue
        if not isinstance(content_text, str) or not content_text.strip():
            continue
        if not isinstance(requires, bool):
            requires = False
        cleaned.append(
            {
                "block_type": block_type,
                "content": content_text.strip(),
                "requires_judgement_run": bool(requires),
            }
        )
    return cleaned or None


@app.post("/draft")
async def draft(request: dict[str, Any]) -> JSONResponse:
    required = ["draft_request_id", "requested_at", "requested_by", "artefact_type", "time_budget_seconds"]
    missing = [k for k in required if k not in request]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    artefact_type = request.get("artefact_type")
    time_budget_seconds = float(request.get("time_budget_seconds") or 10)

    llm_blocks = await _llm_blocks(draft_request=request, time_budget_seconds=time_budget_seconds)
    if llm_blocks is None:
        llm_blocks = [
            {
                "block_type": "heading",
                "content": "Draft (starter)",
                "requires_judgement_run": False,
            },
            {
                "block_type": "paragraph",
                "content": (
                    "This is a quick draft starter intended for planner review. "
                    "Next: bind claims to evidence cards and run a judgement pass where needed."
                ),
                "requires_judgement_run": False,
            },
        ]

    suggestions: list[dict[str, Any]] = []
    for block in llm_blocks:
        suggestions.append(
            {
                "suggestion_id": str(uuid4()),
                "block_type": block["block_type"],
                "content": block["content"],
                "evidence_refs": [],
                "assumption_ids": [],
                "limitations_text": (
                    None
                    if block.get("requires_judgement_run") is False
                    else "Requires a full judgement run before sign-off."
                ),
                "requires_judgement_run": bool(block.get("requires_judgement_run")),
                "insertion_hint": {"artefact_type": artefact_type},
            }
        )

    pack = {
        "draft_pack_id": str(uuid4()),
        "draft_request_id": request["draft_request_id"],
        "status": "complete",
        "suggestions": suggestions,
        "tool_run_ids": [],
        "created_at": _utc_now_iso(),
    }
    return JSONResponse(content=pack)


@app.get("/spec/schemas")
def list_schemas() -> dict[str, list[str]]:
    root = _spec_root()
    schemas_dir = root / "schemas"
    if not schemas_dir.exists():
        raise HTTPException(status_code=404, detail="schemas directory missing in spec root")
    names = sorted(p.name for p in schemas_dir.glob("*.schema.json"))
    return {"schemas": names}


@app.get("/spec/schemas/{schema_name}")
def get_schema(schema_name: str) -> JSONResponse:
    if "/" in schema_name or ".." in schema_name:
        raise HTTPException(status_code=400, detail="Invalid schema name")
    root = _spec_root()
    schema_path = root / "schemas" / schema_name
    if not schema_path.name.endswith(".schema.json"):
        raise HTTPException(status_code=400, detail="Schema name must end with .schema.json")
    return JSONResponse(content=_read_json(schema_path))
