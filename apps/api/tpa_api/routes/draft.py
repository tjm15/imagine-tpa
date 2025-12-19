from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..model_clients import _ensure_model_role, _llm_model_id
from ..retrieval import _gather_draft_evidence
from ..text_utils import _extract_json_object
from ..time_utils import _utc_now_iso


router = APIRouter(tags=["drafts"])


async def _llm_blocks(
    *,
    draft_request: dict[str, Any],
    time_budget_seconds: float,
    evidence_context: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    base_url = await _ensure_model_role(role="llm", timeout_seconds=180.0) or os.environ.get("TPA_LLM_BASE_URL")
    if not base_url:
        return None

    model = _llm_model_id()
    timeout = min(max(time_budget_seconds, 1.0), 60.0)

    system = (
        "You are The Planner's Assistant. Produce a quick first draft for a UK planning professional. "
        "You will be given an evidence_context list. When you make factual claims, cite relevant evidence "
        "by including EvidenceRef strings in an 'evidence_refs' array per block. "
        "Return ONLY valid JSON with this shape: "
        '{ "blocks": [ {"block_type": "heading|paragraph|bullets|callout|other", "content": string, '
        '"evidence_refs": string[], "requires_judgement_run": boolean } ] }. '
        "Keep it concise and useful. Do not include markdown fences."
    )
    user = json.dumps({"draft_request": draft_request, "evidence_context": evidence_context or []}, ensure_ascii=False)

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
    except Exception:  # noqa: BLE001
        return None

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001
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
        evidence_refs = b.get("evidence_refs")
        requires = b.get("requires_judgement_run")
        if block_type not in {"heading", "paragraph", "bullets", "callout", "other"}:
            continue
        if not isinstance(content_text, str) or not content_text.strip():
            continue
        if not isinstance(evidence_refs, list):
            evidence_refs = []
        cleaned_refs = [r for r in evidence_refs if isinstance(r, str) and "::" in r][:10]
        if not isinstance(requires, bool):
            requires = False
        cleaned.append(
            {
                "block_type": block_type,
                "content": content_text.strip(),
                "evidence_refs": cleaned_refs,
                "requires_judgement_run": bool(requires),
            }
        )
    return cleaned or None


@router.post("/draft")
async def draft(request: dict[str, Any]) -> JSONResponse:
    required = ["draft_request_id", "requested_at", "requested_by", "artefact_type", "time_budget_seconds"]
    missing = [k for k in required if k not in request]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    artefact_type = request.get("artefact_type")
    time_budget_seconds = float(request.get("time_budget_seconds") or 10)

    constraints = request.get("constraints") if isinstance(request.get("constraints"), dict) else {}
    authority_id = constraints.get("authority_id") if isinstance(constraints.get("authority_id"), str) else None
    plan_cycle_id = constraints.get("plan_cycle_id") if isinstance(constraints.get("plan_cycle_id"), str) else None
    query_text = (request.get("user_prompt") or "") if isinstance(request.get("user_prompt"), str) else ""
    if not query_text.strip():
        query_text = str(artefact_type or "draft")
    evidence_context = (
        _gather_draft_evidence(authority_id=authority_id, plan_cycle_id=plan_cycle_id, query_text=query_text)
        if authority_id
        else []
    )

    llm_blocks = await _llm_blocks(
        draft_request=request,
        time_budget_seconds=time_budget_seconds,
        evidence_context=evidence_context,
    )
    if llm_blocks is None:
        llm_blocks = [
            {
                "block_type": "heading",
                "content": "Draft (starter)",
                "evidence_refs": [],
                "requires_judgement_run": False,
            },
            {
                "block_type": "paragraph",
                "content": (
                    "This is a quick draft starter intended for planner review. "
                    "Next: bind claims to evidence cards and run a judgement pass where needed."
                ),
                "evidence_refs": [],
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
                "evidence_refs": block.get("evidence_refs", []) or [],
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

