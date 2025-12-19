from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def minio_client_or_none() -> Any | None:
    endpoint = os.environ.get("TPA_S3_ENDPOINT")
    access_key = os.environ.get("TPA_S3_ACCESS_KEY")
    secret_key = os.environ.get("TPA_S3_SECRET_KEY")
    bucket = os.environ.get("TPA_S3_BUCKET")
    if not endpoint or not access_key or not secret_key or not bucket:
        return None
    try:
        from minio import Minio
    except Exception:  # noqa: BLE001
        return None

    parsed = urlparse(endpoint)
    host = parsed.netloc or parsed.path
    secure = parsed.scheme == "https"
    return Minio(host, access_key=access_key, secret_key=secret_key, secure=secure)


def read_blob_bytes(blob_path: str) -> tuple[bytes | None, str | None, str | None]:
    """
    Best-effort blob loader for OSS dev:
    - if blob_path is a readable local file path, load it
    - else, treat blob_path as an object name in the configured MinIO bucket

    Returns (bytes, content_type, error_text).
    """
    if not blob_path:
        return None, None, "empty_blob_path"

    local = Path(blob_path)
    if local.exists() and local.is_file():
        try:
            data = local.read_bytes()
            content_type = mimetypes.guess_type(local.name)[0] or "application/octet-stream"
            return data, content_type, None
        except Exception as exc:  # noqa: BLE001
            return None, None, f"read_local_failed: {exc}"

    client = minio_client_or_none()
    bucket = os.environ.get("TPA_S3_BUCKET")
    if not client or not bucket:
        return None, None, "minio_unconfigured"

    try:
        resp = client.get_object(bucket, blob_path)
        try:
            data = resp.read()
        finally:
            resp.close()
            resp.release_conn()
        content_type = mimetypes.guess_type(blob_path)[0] or "application/octet-stream"
        return data, content_type, None
    except Exception as exc:  # noqa: BLE001
        return None, None, f"minio_get_object_failed: {exc}"


def to_data_url(data: bytes, content_type: str) -> str:
    b64 = base64.b64encode(data).decode("ascii")
    ct = content_type or "application/octet-stream"
    return f"data:{ct};base64,{b64}"

