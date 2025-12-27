from __future__ import annotations

import io
import json
import os
from typing import Any
from uuid import uuid4

import httpx

from tpa_api.blob_store import minio_client_or_none
from tpa_api.db import _db_execute
from tpa_api.time_utils import _utc_now


def _load_parse_bundle(blob_path: str) -> dict[str, Any]:
    client = minio_client_or_none()
    bucket = os.environ.get("TPA_S3_BUCKET")
    if not client or not bucket:
        raise RuntimeError("MinIO not configured for parse bundle retrieval")
    resp = client.get_object(bucket, blob_path)
    try:
        data = resp.read()
    finally:
        resp.close()
        resp.release_conn()
    return json.loads(data)


def _call_docparse_bundle(
    *,
    file_bytes: bytes,
    filename: str,
    metadata: dict[str, Any],
    ingest_batch_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    base_url = os.environ.get("TPA_DOCPARSE_BASE_URL")
    if not base_url:
        raise RuntimeError("TPA_DOCPARSE_BASE_URL not configured")
    url = base_url.rstrip("/") + "/parse/bundle"
    files = {"file": (filename, io.BytesIO(file_bytes), "application/pdf")}
    data = {"metadata": json.dumps(metadata, ensure_ascii=False)}
    timeout = None
    tool_run_id = str(uuid4())
    started_at = _utc_now()
    tool_run_inserted = False
    try:
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
              started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, %s, %s)
            """,
            (
                tool_run_id,
                ingest_batch_id,
                run_id,
                "docparse_bundle",
                json.dumps(
                    {
                        "filename": filename,
                        "byte_count": len(file_bytes),
                        "base_url": base_url,
                    },
                    ensure_ascii=False,
                ),
                json.dumps({}, ensure_ascii=False),
                "running",
                started_at,
                "low",
                "Docparse bundle request in progress.",
            ),
        )
        tool_run_inserted = True
    except Exception:  # noqa: BLE001
        tool_run_inserted = False

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, files=files, data=data)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        if tool_run_inserted:
            try:
                _db_execute(
                    """
                    UPDATE tool_runs
                    SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                        confidence_hint = %s, uncertainty_note = %s
                    WHERE id = %s::uuid
                    """,
                    (
                        "error",
                        json.dumps({"error": str(exc)}, ensure_ascii=False),
                        _utc_now(),
                        "low",
                        "Docparse request failed; check docparse service logs.",
                        tool_run_id,
                    ),
                )
            except Exception:  # noqa: BLE001
                pass
        raise

    if tool_run_inserted:
        try:
            _db_execute(
                """
                UPDATE tool_runs
                SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                    confidence_hint = %s, uncertainty_note = %s
                WHERE id = %s::uuid
                """,
                (
                    "success",
                    json.dumps(
                        {
                            "parse_bundle_path": payload.get("parse_bundle_path"),
                            "schema_version": payload.get("schema_version"),
                            "parse_flags": payload.get("parse_flags"),
                        },
                        ensure_ascii=False,
                    ),
                    _utc_now(),
                    "medium",
                    "Docparse bundle returned successfully.",
                    tool_run_id,
                ),
            )
        except Exception:  # noqa: BLE001
            pass

    return payload


def _persist_tool_runs(
    *,
    ingest_batch_id: str,
    run_id: str | None,
    tool_runs: list[dict[str, Any]],
) -> list[str]:
    tool_run_ids: list[str] = []
    for tr in tool_runs:
        tool_run_id = str(uuid4())
        tool_run_ids.append(tool_run_id)
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
              started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                tool_run_id,
                ingest_batch_id,
                run_id,
                tr.get("tool_name") or "docparse_tool",
                json.dumps(tr.get("inputs") or {}, ensure_ascii=False),
                json.dumps(tr.get("outputs") or {}, ensure_ascii=False),
                tr.get("status") or "success",
                _utc_now(),
                _utc_now(),
                tr.get("confidence_hint"),
                tr.get("limitations_text"),
            ),
        )
    return tool_run_ids


def _insert_parse_bundle_record(
    *,
    ingest_job_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    document_id: str,
    schema_version: str,
    blob_path: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    bundle_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO parse_bundles (
          id, ingest_job_id, ingest_batch_id, run_id, document_id,
          schema_version, blob_path, status, metadata_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s::jsonb, %s)
        """,
        (
            bundle_id,
            ingest_job_id,
            ingest_batch_id,
            run_id,
            document_id,
            schema_version,
            blob_path,
            "stored",
            json.dumps(metadata or {}, ensure_ascii=False),
            _utc_now(),
        ),
    )
    return bundle_id
