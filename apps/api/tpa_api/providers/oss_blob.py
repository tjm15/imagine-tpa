from __future__ import annotations

import io
import json
import mimetypes
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

from tpa_api.blob_store import minio_client_or_none
from tpa_api.db import _db_execute
from tpa_api.providers.base import BlobStoreProvider
from tpa_api.time_utils import _utc_now


class MinIOBlobStoreProvider(BlobStoreProvider):
    """
    OSS implementation of BlobStoreProvider using MinIO.
    """

    def __init__(self, bucket: str | None = None):
        self._client = minio_client_or_none()
        self._bucket = bucket or os.environ.get("TPA_S3_BUCKET")
        if not self._client or not self._bucket:
            # We don't raise here to allow the runtime to fail-fast during actual calls
            # if configuration is missing, but it's better to have a working client.
            pass

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
        run_id: str | None = None,
        ingest_batch_id: str | None = None,
    ) -> str:
        tool_run_id = str(uuid4())
        inputs_payload = inputs if os.environ.get("TPA_LOG_S3_INPUTS") == "true" else {}
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, tool_name, inputs_logged, outputs_logged, status,
              started_at, ended_at, uncertainty_note, run_id, ingest_batch_id
            )
            VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s::uuid, %s::uuid)
            """,
            (
                tool_run_id,
                tool_name,
                json.dumps(inputs_payload, default=str),
                json.dumps(outputs, default=str),
                status,
                started_at,
                _utc_now(),
                error_text,
                run_id,
                ingest_batch_id,
            ),
        )
        return tool_run_id

    def put_blob(
        self,
        path: str,
        data: bytes,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        run_id: str | None = None,
        ingest_batch_id: str | None = None,
    ) -> dict[str, Any]:
        started_at = _utc_now()
        if not self._client or not self._bucket:
            err = "MinIO not configured"
            self._log_tool_run("blob.put", {"path": path}, {"error": err}, "error", started_at, err, run_id, ingest_batch_id)
            raise RuntimeError(err)

        ct = content_type or mimetypes.guess_type(path)[0] or "application/octet-stream"
        try:
            # Ensure bucket exists
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)

            result = self._client.put_object(
                self._bucket,
                path,
                io.BytesIO(data),
                length=len(data),
                content_type=ct,
                metadata=metadata,
            )
            outputs = {
                "path": path,
                "etag": result.etag,
                "size_bytes": len(data),
                "content_type": ct,
            }
            self._log_tool_run("blob.put", {"path": path, "size": len(data)}, outputs, "success", started_at, run_id=run_id, ingest_batch_id=ingest_batch_id)
            return outputs
        except Exception as exc:
            err = str(exc)
            self._log_tool_run("blob.put", {"path": path}, {"error": err}, "error", started_at, err, run_id, ingest_batch_id)
            raise

    def get_blob(self, path: str, run_id: str | None = None, ingest_batch_id: str | None = None) -> dict[str, Any]:
        started_at = _utc_now()
        if not self._client or not self._bucket:
            err = "MinIO not configured"
            self._log_tool_run("blob.get", {"path": path}, {"error": err}, "error", started_at, err, run_id, ingest_batch_id)
            raise RuntimeError(err)

        try:
            resp = self._client.get_object(self._bucket, path)
            try:
                data = resp.read()
                # MinIO metadata is returned in headers, often prefixed with x-amz-meta-
                metadata = {k: v for k, v in resp.headers.items() if k.lower().startswith("x-amz-meta-")}
                content_type = resp.headers.get("content-type") or "application/octet-stream"
            finally:
                resp.close()
                resp.release_conn()

            outputs = {
                "size_bytes": len(data),
                "content_type": content_type,
            }
            self._log_tool_run("blob.get", {"path": path}, outputs, "success", started_at, run_id=run_id, ingest_batch_id=ingest_batch_id)
            return {"bytes": data, "content_type": content_type, "metadata": metadata}
        except Exception as exc:
            err = str(exc)
            self._log_tool_run("blob.get", {"path": path}, {"error": err}, "error", started_at, err, run_id, ingest_batch_id)
            raise

    def delete_blob(self, path: str, run_id: str | None = None, ingest_batch_id: str | None = None) -> None:
        started_at = _utc_now()
        if not self._client or not self._bucket:
            raise RuntimeError("MinIO not configured")

        try:
            self._client.remove_object(self._bucket, path)
            self._log_tool_run("blob.delete", {"path": path}, {}, "success", started_at, run_id=run_id, ingest_batch_id=ingest_batch_id)
        except Exception as exc:
            err = str(exc)
            self._log_tool_run("blob.delete", {"path": path}, {"error": err}, "error", started_at, err, run_id, ingest_batch_id)
            raise

    def exists(self, path: str) -> bool:
        if not self._client or not self._bucket:
            return False
        try:
            self._client.stat_object(self._bucket, path)
            return True
        except Exception:
            return False
