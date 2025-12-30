from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx

from tpa_api.db import _db_execute
from tpa_api.model_clients import _llm_model_id, _resolve_model_base_url_sync
from tpa_api.providers.llm import LLMProvider
from tpa_api.time_utils import _utc_now
from tpa_api.text_utils import _extract_json_object


class OpenAILLMProvider(LLMProvider):
    """
    OpenAI-compatible implementation of LLMProvider.
    """

    @property
    def profile_family(self) -> str:
        return "oss" # Works for Azure too via base_url

    def _log_tool_run(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        status: str,
        started_at: datetime,
        error_text: str | None = None,
        confidence_hint: str = "medium",
        uncertainty_note: str | None = None,
        run_id: str | None = None,
        ingest_batch_id: str | None = None,
    ) -> str:
        tool_run_id = str(uuid4())
        inputs_json = json.dumps(inputs, ensure_ascii=False, default=str)
        outputs_json = json.dumps(outputs, ensure_ascii=False, default=str)
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, tool_name, inputs_logged, outputs_logged, status,
              started_at, ended_at, confidence_hint, uncertainty_note, run_id, ingest_batch_id
            )
            VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s::uuid, %s::uuid)
            """,
            (
                tool_run_id,
                tool_name,
                inputs_json,
                outputs_json,
                status,
                started_at,
                _utc_now(),
                confidence_hint,
                uncertainty_note,
                run_id,
                ingest_batch_id,
            ),
        )
        return tool_run_id

    def generate_structured(
        self,
        messages: list[dict[str, str]],
        json_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started_at = _utc_now()
        options = options or {}
        run_id = options.get("run_id")
        ingest_batch_id = options.get("ingest_batch_id")
        
        # Resolve base URL
        base_url = _resolve_model_base_url_sync(role="llm", env_key="TPA_LLM_BASE_URL", timeout_seconds=180.0)
        if not base_url:
            err = "model_supervisor_unavailable:llm" if os.environ.get("TPA_MODEL_SUPERVISOR_URL") else "TPA_LLM_BASE_URL not configured"
            self._log_tool_run(
                "llm.generate_structured",
                {"messages": messages},
                {"error": err},
                "error",
                started_at,
                error_text=err,
                run_id=run_id,
                ingest_batch_id=ingest_batch_id
            )
            raise RuntimeError(err)

        model_id = options.get("model_id") or _llm_model_id()
        url = base_url.rstrip("/") + "/chat/completions"
        
        # Prepare payload
        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": options.get("temperature", 0.0),
        }
        
        if options.get("max_tokens"):
            payload["max_tokens"] = options.get("max_tokens")

        # Handle JSON schema if supported by the provider directly (e.g. OpenAI structured outputs)
        # For generic OSS/vLLM, we might just rely on prompt engineering or grammar constraints.
        # Here we assume standard chat completions and post-processing.
        
        inputs_logged = {
            "model_id": model_id,
            "message_count": len(messages),
            # Log full messages if configured, otherwise truncate or summarize?
            # Spec says "fully materialised prompt", so we log it.
            "messages": messages, 
            "options": options
        }

        try:
            with httpx.Client(timeout=180.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            choice = data["choices"][0]
            raw_text = choice["message"]["content"]
            usage = data.get("usage", {})
            
            # Extract JSON
            json_obj = _extract_json_object(raw_text)
            
            # Validate if schema provided (simple check for now)
            # In a full implementation, use jsonschema.validate(json_obj, json_schema)
            
            outputs_logged = {
                "ok": json_obj is not None,
                "usage": usage,
                "raw_text_preview": (raw_text or "")[:1000]
            }
            
            status = "success" if json_obj is not None else "partial"
            error_text = None if json_obj is not None else "Failed to parse JSON from LLM output"

            tool_run_id = self._log_tool_run(
                "llm.generate_structured",
                inputs_logged,
                outputs_logged,
                status,
                started_at,
                error_text=error_text,
                confidence_hint="medium" if json_obj else "low",
                run_id=run_id,
                ingest_batch_id=ingest_batch_id
            )
            
            return {
                "json": json_obj,
                "usage": usage,
                "model_id": model_id,
                "raw_text": raw_text,
                "tool_run_id": tool_run_id
            }

        except Exception as exc:
            err = str(exc)
            self._log_tool_run(
                "llm.generate_structured",
                inputs_logged,
                {"error": err},
                "error",
                started_at,
                error_text=f"LLM call failed: {err}",
                confidence_hint="low",
                run_id=run_id,
                ingest_batch_id=ingest_batch_id
            )
            raise RuntimeError(f"LLM call failed: {err}") from exc
