from __future__ import annotations

import io
import json
import os
import threading
import time
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
                json.dumps(inputs, default=str),
                json.dumps(outputs, default=str),
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
        started_monotonic = time.monotonic()
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
                ingest_batch_id=ingest_batch_id,
            )
            raise RuntimeError(err)

        url = base_url.rstrip("/") + "/parse/bundle"

        metadata = {
            "source_filename": filename,
            "blob_path": blob_path,
            **options.get("metadata", {}),
        }

        inputs_logged = {
            "filename": filename,
            "byte_count": len(file_bytes),
            "base_url": base_url,
            "metadata": metadata,
        }

        tool_run_id = str(uuid4())
        tool_run_inserted = False
        try:
            _db_execute(
                """
                INSERT INTO tool_runs (
                  id, tool_name, inputs_logged, outputs_logged, status,
                  started_at, ended_at, confidence_hint, uncertainty_note, run_id, ingest_batch_id
                )
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, %s, %s, %s::uuid, %s::uuid)
                """,
                (
                    tool_run_id,
                    "docparse.parse_document",
                    json.dumps(inputs_logged, default=str),
                    json.dumps({}, default=str),
                    "running",
                    started_at,
                    "low",
                    "Docparse request in progress.",
                    run_id,
                    ingest_batch_id,
                ),
            )
            tool_run_inserted = True
        except Exception:  # noqa: BLE001
            tool_run_inserted = False

        stop_event = threading.Event()

        def _heartbeat() -> None:
            while not stop_event.wait(30.0):
                elapsed = int(time.monotonic() - started_monotonic)
                payload = {"progress": "running", "elapsed_seconds": elapsed}
                try:
                    _db_execute(
                        """
                        UPDATE tool_runs
                        SET outputs_logged = outputs_logged || %s::jsonb,
                            ended_at = %s
                        WHERE id = %s::uuid
                        """,
                        (
                            json.dumps(payload, default=str),
                            _utc_now(),
                            tool_run_id,
                        ),
                    )
                except Exception:  # noqa: BLE001
                    pass

        if tool_run_inserted:
            threading.Thread(target=_heartbeat, daemon=True).start()

        try:
            files = {"file": (filename, io.BytesIO(file_bytes), "application/pdf")}
            data = {"metadata": json.dumps(metadata, ensure_ascii=False, default=str)}

            with httpx.Client(timeout=None) as client:
                resp = client.post(url, files=files, data=data)
                resp.raise_for_status()
                payload = resp.json()

            outputs_logged = {
                "parse_bundle_path": payload.get("parse_bundle_path"),
                "schema_version": payload.get("schema_version"),
                "parse_flags": payload.get("parse_flags"),
                "page_count": len(payload.get("pages") or []) if payload.get("pages") else 0,
            }

            if tool_run_inserted:
                stop_event.set()
                _db_execute(
                    """
                    UPDATE tool_runs
                    SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                        confidence_hint = %s, uncertainty_note = %s
                    WHERE id = %s::uuid
                    """,
                    (
                        "success",
                        json.dumps(outputs_logged, default=str),
                        _utc_now(),
                        "high",
                        "Docparse bundle returned successfully.",
                        tool_run_id,
                    ),
                )
            else:
                self._log_tool_run(
                    "docparse.parse_document",
                    inputs_logged,
                    outputs_logged,
                    "success",
                    started_at,
                    confidence_hint="high",
                    uncertainty_note="Docparse bundle returned successfully.",
                    run_id=run_id,
                    ingest_batch_id=ingest_batch_id,
                )
            return payload

        except Exception as exc:
            err = str(exc)
            if tool_run_inserted:
                stop_event.set()
                _db_execute(
                    """
                    UPDATE tool_runs
                    SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                        confidence_hint = %s, uncertainty_note = %s
                    WHERE id = %s::uuid
                    """,
                    (
                        "error",
                        json.dumps({"error": err}, default=str),
                        _utc_now(),
                        "low",
                        f"DocParse request failed: {err}",
                        tool_run_id,
                    ),
                )
            else:
                self._log_tool_run(
                    "docparse.parse_document",
                    inputs_logged,
                    {"error": err},
                    "error",
                    started_at,
                    error_text=f"DocParse request failed: {err}",
                    confidence_hint="low",
                    run_id=run_id,
                    ingest_batch_id=ingest_batch_id,
                )
            raise RuntimeError(f"DocParse failed: {err}") from exc
