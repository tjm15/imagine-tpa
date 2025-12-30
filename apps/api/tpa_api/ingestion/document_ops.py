from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from tpa_api.db import _db_execute, _db_fetch_one


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ensure_artifact(*, artifact_type: str, path: str) -> str:
    existing = _db_fetch_one("SELECT id FROM artifacts WHERE type = %s AND path = %s", (artifact_type, path))
    if existing:
        return str(existing["id"])
    artifact_id = str(uuid4())
    _db_execute(
        "INSERT INTO artifacts (id, type, path) VALUES (%s, %s, %s)",
        (artifact_id, artifact_type, path),
    )
    return artifact_id


def _ensure_document_row(
    *,
    authority_id: str,
    plan_cycle_id: str,
    ingest_batch_id: str,
    run_id: str | None,
    blob_path: str,
    metadata: dict[str, Any],
    raw_blob_path: str | None = None,
    raw_sha256: str | None = None,
    raw_bytes: int | None = None,
    raw_content_type: str | None = None,
    raw_source_uri: str | None = None,
    raw_artifact_id: str | None = None,
) -> str:
    existing = None
    if raw_sha256:
        existing = _db_fetch_one(
            """
            SELECT id, raw_blob_path, raw_sha256
            FROM documents
            WHERE authority_id = %s
              AND plan_cycle_id = %s::uuid
              AND raw_sha256 = %s
            """,
            (authority_id, plan_cycle_id, raw_sha256),
        )
    if not existing:
        existing = _db_fetch_one(
            """
            SELECT id FROM documents
            WHERE authority_id = %s
              AND plan_cycle_id = %s::uuid
              AND blob_path = %s
            """,
            (authority_id, plan_cycle_id, blob_path),
        )
    if existing:
        doc_id = str(existing["id"])
        _db_execute(
            """
            UPDATE documents
            SET ingest_batch_id = %s::uuid,
                plan_cycle_id = COALESCE(plan_cycle_id, %s::uuid),
                raw_blob_path = COALESCE(raw_blob_path, %s),
                raw_sha256 = COALESCE(raw_sha256, %s),
                raw_bytes = COALESCE(raw_bytes, %s),
                raw_content_type = COALESCE(raw_content_type, %s),
                raw_source_uri = COALESCE(raw_source_uri, %s),
                raw_artifact_id = COALESCE(raw_artifact_id, %s::uuid),
                run_id = COALESCE(run_id, %s::uuid)
            WHERE id = %s::uuid
            """,
            (
                ingest_batch_id,
                plan_cycle_id,
                raw_blob_path,
                raw_sha256,
                raw_bytes,
                raw_content_type,
                raw_source_uri,
                raw_artifact_id,
                run_id,
                doc_id,
            ),
        )
        return doc_id
    doc_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO documents (
          id, authority_id, ingest_batch_id, plan_cycle_id, run_id,
          document_status, weight_hint, effective_from, effective_to,
          metadata, blob_path, raw_blob_path, raw_sha256, raw_bytes,
          raw_content_type, raw_source_uri, raw_artifact_id
        )
        VALUES (%s, %s, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s::uuid)
        """,
        (
            doc_id,
            authority_id,
            ingest_batch_id,
            plan_cycle_id,
            run_id,
            metadata.get("status"),
            metadata.get("weight_hint"),
            metadata.get("effective_from"),
            metadata.get("effective_to"),
            json.dumps(metadata, ensure_ascii=False),
            blob_path,
            raw_blob_path,
            raw_sha256,
            raw_bytes,
            raw_content_type,
            raw_source_uri,
            raw_artifact_id,
        ),
    )
    return doc_id


def _store_raw_blob(
    *,
    client: Any | None,
    bucket: str | None,
    authority_id: str,
    filename: str,
    data: bytes,
) -> tuple[str, str]:
    sha = _hash_bytes(data)
    ext = Path(filename).suffix or ".pdf"
    object_name = f"raw/{authority_id}/{sha}{ext}"
    if not client or not bucket:
        raise RuntimeError("MinIO not configured for raw artifact storage")
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"MinIO bucket ensure failed: {exc}") from exc
    try:
        client.stat_object(bucket, object_name)
    except Exception:  # noqa: BLE001
        client.put_object(bucket, object_name, io.BytesIO(data), length=len(data), content_type="application/pdf")
    return object_name, sha
