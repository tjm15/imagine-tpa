from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx

from tpa_api.db import _db_execute
from tpa_api.model_clients import _resolve_model_base_url_sync, _vlm_model_id
from tpa_api.providers.vlm import VLMProvider
from tpa_api.time_utils import _utc_now
from tpa_api.text_utils import _extract_json_object


class OpenAIVLMProvider(VLMProvider):
    """
    OpenAI-compatible implementation of VLMProvider.
    Supports GPT-4o, GPT-4-turbo, Qwen2-VL, etc.
    """

    @property
    def profile_family(self) -> str:
        return "oss"

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
        images: list[bytes],
        json_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started_at = _utc_now()
        options = options or {}
        run_id = options.get("run_id")
        ingest_batch_id = options.get("ingest_batch_id")
        
        base_url = _resolve_model_base_url_sync(role="vlm", env_key="TPA_VLM_BASE_URL", timeout_seconds=300.0)
        if not base_url:
            err = "model_supervisor_unavailable:vlm" if os.environ.get("TPA_MODEL_SUPERVISOR_URL") else "TPA_VLM_BASE_URL not configured"
            self._log_tool_run(
                "vlm.generate_structured",
                {"message_count": len(messages), "image_count": len(images)},
                {"error": err},
                "error",
                started_at,
                error_text=err,
                run_id=run_id,
                ingest_batch_id=ingest_batch_id
            )
            raise RuntimeError(err)

        model_id = options.get("model_id") or _vlm_model_id()
        url = base_url.rstrip("/") + "/chat/completions"
        
        # Prepare content list for the user message
        content_parts: list[dict[str, Any]] = []
        
        # Append text messages (system instructions typically go in separate messages, 
        # but user text accompanies images in the 'user' message content list).
        
        # We need to construct the API payload carefully.
        # OpenAI style: 
        # messages=[
        #   {"role": "system", "content": "..."},
        #   {"role": "user", "content": [
        #       {"type": "text", "text": "..."},
        #       {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
        #   ]}
        # ]
        
        # Separate system messages from user messages
        final_messages: list[dict[str, Any]] = []
        user_text_parts: list[str] = []
        
        for msg in messages:
            if msg["role"] == "system":
                final_messages.append({"role": "system", "content": msg["content"]})
            else:
                user_text_parts.append(msg["content"])
        
        user_content: list[dict[str, Any]] = []
        if user_text_parts:
            user_content.append({"type": "text", "text": "\n\n".join(user_text_parts)})
            
        for img_bytes in images:
            b64_str = base64.b64encode(img_bytes).decode("ascii")
            # Assume PNG/JPEG compatible. OpenAI detects mime usually, or we can guess.
            # Safe default is data:image/jpeg;base64 for generic usage or sniff bytes.
            # We'll use a generic prefix or provider logic if strictness required.
            mime = "image/jpeg" # Default
            if img_bytes.startswith(b"\x89PNG"):
                mime = "image/png"
            elif img_bytes.startswith(b"GIF8"):
                mime = "image/gif"
            elif img_bytes.startswith(b"RIFF"):
                mime = "image/webp"
                
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64_str}"}
            })
            
        final_messages.append({"role": "user", "content": user_content})
        
        payload = {
            "model": model_id,
            "messages": final_messages,
            "temperature": options.get("temperature", 0.0),
            "max_tokens": options.get("max_tokens", 4000)
        }

        # Logging inputs (don't log full base64 images!)
        inputs_logged = {
            "model_id": model_id,
            "messages": messages, # Log the original text-only messages struct
            "image_count": len(images),
            "image_sizes_bytes": [len(b) for b in images],
            "options": options
        }

        try:
            # Huge timeout for VLMs
            with httpx.Client(timeout=300.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            choice = data["choices"][0]
            raw_text = choice["message"]["content"]
            usage = data.get("usage", {})
            
            json_obj = _extract_json_object(raw_text)
            
            status = "success" if json_obj is not None else "partial"
            error_text = None if json_obj is not None else "Failed to parse JSON from VLM output"
            
            outputs_logged = {
                "ok": json_obj is not None,
                "usage": usage,
                "raw_text_preview": (raw_text or "")[:1000]
            }

            tool_run_id = self._log_tool_run(
                "vlm.generate_structured",
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
                "vlm.generate_structured",
                inputs_logged,
                {"error": err},
                "error",
                started_at,
                error_text=f"VLM call failed: {err}",
                confidence_hint="low",
                run_id=run_id,
                ingest_batch_id=ingest_batch_id
            )
            raise RuntimeError(f"VLM call failed: {err}") from exc
