from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException


def validate_uuid_or_400(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(value))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{field_name} must be a UUID") from exc

