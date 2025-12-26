from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx

from tpa_api.db import _db_execute
from tpa_api.providers.vectorization import VectorizationProvider
from tpa_api.time_utils import _utc_now


class HttpVectorizationProvider(VectorizationProvider):
    """
    HTTP-based implementation of VectorizationProvider.
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
                inputs,
                outputs,
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

    def vectorize(
        self,
        image: bytes,
        prompts: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started_at = _utc_now()
        options = options or {}
        run_id = options.get("run_id")
        ingest_batch_id = options.get("ingest_batch_id")

        base_url = os.environ.get("TPA_VECTORIZE_BASE_URL")
        if not base_url:
            err = "TPA_VECTORIZE_BASE_URL not configured"
            self._log_tool_run(
                "vectorization.vectorize",
                {"prompts": prompts},
                {"error": err},
                "error",
                started_at,
                error_text=err,
                run_id=run_id,
                ingest_batch_id=ingest_batch_id
            )
            raise RuntimeError(err)

        url = base_url.rstrip("/") + "/vectorize"
        
        inputs_logged = {
            "image_bytes": len(image),
            "base_url": base_url,
            "options": options
        }

        try:
            payload = {
                "mask_png_base64": base64.b64encode(image).decode("ascii"),
                # The generic interface calls it 'image', but the specific service expects 'mask_png_base64'
                # for the current use case. A more generic 'image_base64' might be better for v2.
            }
            
            with httpx.Client(timeout=180.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            features = data.get("features_geojson", {}).get("features", [])
            outputs_logged = {
                "feature_count": len(features),
                "confidence": data.get("confidence")
            }

            self._log_tool_run(
                "vectorization.vectorize",
                inputs_logged,
                outputs_logged,
                "success",
                started_at,
                confidence_hint="high",
                uncertainty_note=data.get("limitations_text"),
                run_id=run_id,
                ingest_batch_id=ingest_batch_id
            )
            return data

        except Exception as exc:
            err = str(exc)
            self._log_tool_run(
                "vectorization.vectorize",
                inputs_logged,
                {"error": err},
                "error",
                started_at,
                error_text=f"Vectorization failed: {err}",
                confidence_hint="low",
                run_id=run_id,
                ingest_batch_id=ingest_batch_id
            )
            raise RuntimeError(f"Vectorization failed: {err}") from exc
