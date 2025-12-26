from __future__ import annotations

import io
import json
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx

from tpa_api.db import _db_execute
from tpa_api.providers.docparse import DocParseProvider
from tpa_api.time_utils import _utc_now


class HttpDocParseProvider(DocParseProvider):
    """
    HTTP-based implementation of DocParseProvider.
    Connects to the tpa-docparse service.
    """

    @property
    def profile_family(self) -> str:
        return "oss"  # Also valid for Azure if using a containerized service

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

    def parse_document(
        self,
        blob_path: str,
        file_bytes: bytes,
        filename: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started_at = _utc_now()
        options = options or {}
        run_id = options.get("run_id")
        ingest_batch_id = options.get("ingest_batch_id")

        base_url = os.environ.get("TPA_DOCPARSE_BASE_URL")
        if not base_url:
            err = "TPA_DOCPARSE_BASE_URL not configured"
            self._log_tool_run(
                "docparse.parse_document",
                {"filename": filename, "blob_path": blob_path},
                {"error": err},
                "error",
                started_at,
                error_text=err,
                run_id=run_id,
                ingest_batch_id=ingest_batch_id
            )
            raise RuntimeError(err)

        url = base_url.rstrip("/") + "/parse/bundle"
        
        # Prepare metadata for the service
        metadata = {
            "source_filename": filename,
            "blob_path": blob_path,
            **options.get("metadata", {})
        }

        inputs_logged = {
            "filename": filename,
            "byte_count": len(file_bytes),
            "base_url": base_url,
            "metadata": metadata
        }

        try:
            files = {"file": (filename, io.BytesIO(file_bytes), "application/pdf")}
            data = {"metadata": json.dumps(metadata, ensure_ascii=False)}
            
            # Using a relatively long timeout as parsing can be slow
            with httpx.Client(timeout=180.0) as client:
                resp = client.post(url, files=files, data=data)
                resp.raise_for_status()
                payload = resp.json()

            outputs_logged = {
                "parse_bundle_path": payload.get("parse_bundle_path"),
                "schema_version": payload.get("schema_version"),
                "parse_flags": payload.get("parse_flags"),
                "page_count": len(payload.get("pages") or []) if payload.get("pages") else 0
            }

            self._log_tool_run(
                "docparse.parse_document",
                inputs_logged,
                outputs_logged,
                "success",
                started_at,
                confidence_hint="high",
                uncertainty_note="Docparse bundle returned successfully.",
                run_id=run_id,
                ingest_batch_id=ingest_batch_id
            )
            return payload

        except Exception as exc:
            err = str(exc)
            self._log_tool_run(
                "docparse.parse_document",
                inputs_logged,
                {"error": err},
                "error",
                started_at,
                error_text=f"DocParse request failed: {err}",
                confidence_hint="low",
                run_id=run_id,
                ingest_batch_id=ingest_batch_id
            )
            raise RuntimeError(f"DocParse failed: {err}") from exc
