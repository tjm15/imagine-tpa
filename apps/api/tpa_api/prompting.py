from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

import httpx

from .db import _db_execute
from .model_clients import _ensure_model_role_sync, _llm_model_id
from .text_utils import _extract_json_object
from .time_utils import _utc_now


def _prompt_upsert(
    *,
    prompt_id: str,
    prompt_version: int,
    name: str,
    purpose: str,
    template: str,
    input_schema_ref: str | None = None,
    output_schema_ref: str | None = None,
    created_by: str = "system",
) -> None:
    now = _utc_now()
    _db_execute(
        """
        INSERT INTO prompts (prompt_id, name, purpose, created_at, created_by)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (prompt_id) DO NOTHING
        """,
        (prompt_id, name, purpose, now, created_by),
    )
    _db_execute(
        """
        INSERT INTO prompt_versions (
          prompt_id, prompt_version, template, input_schema_ref, output_schema_ref,
          created_at, created_by, diff_from_version
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
        ON CONFLICT (prompt_id, prompt_version) DO NOTHING
        """,
        (prompt_id, prompt_version, template, input_schema_ref, output_schema_ref, now, created_by),
    )


def _llm_structured_sync(
    *,
    prompt_id: str,
    prompt_version: int,
    prompt_name: str,
    purpose: str,
    system_template: str,
    user_payload: dict[str, Any],
    time_budget_seconds: float,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model_id: str | None = None,
    output_schema_ref: str | None = None,
    ingest_batch_id: str | None = None,
    run_id: str | None = None,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """
    Calls the configured LLMProvider (OpenAI-compatible) and returns (json, tool_run_id, errors).

    If no LLM is configured, returns (None, None, ["llm_unconfigured"]).
    """
    base_url = _ensure_model_role_sync(role="llm", timeout_seconds=180.0) or os.environ.get("TPA_LLM_BASE_URL")
    if not base_url:
        return None, None, ["llm_unconfigured"]

    model_id = model_id or _llm_model_id()
    timeout = None

    _prompt_upsert(
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        name=prompt_name,
        purpose=purpose,
        template=system_template,
        input_schema_ref=None,
        output_schema_ref=output_schema_ref,
    )

    tool_run_id = str(uuid4())
    started_at = _utc_now()
    url = base_url.rstrip("/") + "/chat/completions"
    errors: list[str] = []
    raw_text: str | None = None
    obj: dict[str, Any] | None = None

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_template},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }
    if temperature is not None:
        payload["temperature"] = float(temperature)
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        raw_text = data["choices"][0]["message"]["content"]
        obj = _extract_json_object(raw_text)
        if not obj:
            errors.append("llm_output_not_json_object")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"llm_call_failed: {exc}")

    ended_at = _utc_now()
    inputs_logged = {
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "prompt_name": prompt_name,
        "purpose": purpose,
        "model_id": model_id,
        "output_schema_ref": output_schema_ref,
        "messages": payload.get("messages"),
    }
    if temperature is not None:
        inputs_logged["temperature"] = temperature
    if max_tokens is not None:
        inputs_logged["max_tokens"] = max_tokens

    _db_execute(
        """
        INSERT INTO tool_runs (
          id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status, started_at, ended_at, confidence_hint, uncertainty_note
        )
        VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
        """,
        (
            tool_run_id,
            ingest_batch_id,
            run_id,
            "llm_generate_structured",
            json.dumps(inputs_logged, ensure_ascii=False),
            json.dumps(
                {
                    "ok": obj is not None,
                    "errors": errors[:10],
                    "raw_text_preview": (raw_text or "")[:1200],
                    "parsed_json": obj if obj is not None else None,
                },
                ensure_ascii=False,
            ),
            "success" if obj is not None and not errors else ("partial" if obj is not None else "error"),
            started_at,
            ended_at,
            "medium" if obj is not None else "low",
            "LLM outputs are non-deterministic; traceability is achieved by persisting move outputs and context bundles.",
        ),
    )

    return obj, tool_run_id, errors
