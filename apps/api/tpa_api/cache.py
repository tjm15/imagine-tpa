from __future__ import annotations

import json
import os
import time
from typing import Any

try:  # optional dependency
    import redis
except Exception:  # noqa: BLE001
    redis = None


_redis_client = None
_memory_cache: dict[str, tuple[Any, float | None]] = {}


def _now() -> float:
    return time.time()


def _get_redis_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if redis is None:
        return None
    url = os.environ.get("TPA_REDIS_URL")
    if not url:
        return None
    try:
        _redis_client = redis.Redis.from_url(url, decode_responses=True)
    except Exception:  # noqa: BLE001
        _redis_client = None
    return _redis_client


def cache_get_json(key: str) -> dict[str, Any] | list[Any] | None:
    client = _get_redis_client()
    if client:
        try:
            raw = client.get(key)
        except Exception:  # noqa: BLE001
            raw = None
        if raw:
            try:
                return json.loads(raw)
            except Exception:  # noqa: BLE001
                return None

    entry = _memory_cache.get(key)
    if not entry:
        return None
    value, expires_at = entry
    if expires_at and expires_at <= _now():
        _memory_cache.pop(key, None)
        return None
    return value


def cache_set_json(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    client = _get_redis_client()
    if client:
        try:
            if ttl_seconds:
                client.setex(key, ttl_seconds, payload)
            else:
                client.set(key, payload)
            return
        except Exception:  # noqa: BLE001
            pass

    expires_at = _now() + ttl_seconds if ttl_seconds else None
    _memory_cache[key] = (value, expires_at)


def cache_delete(key: str) -> None:
    client = _get_redis_client()
    if client:
        try:
            client.delete(key)
        except Exception:  # noqa: BLE001
            pass
    _memory_cache.pop(key, None)


def cache_key(prefix: str, *parts: Any) -> str:
    safe_parts = [str(p) for p in parts if p is not None]
    return ":".join([prefix, *safe_parts])
