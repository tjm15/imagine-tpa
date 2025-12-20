from __future__ import annotations

# Backwards-compatible entrypoint for Docker (`uvicorn tpa_api.main:app`).
from .app import app  # noqa: F401
