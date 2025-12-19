from __future__ import annotations

# Backwards-compatible entrypoint for Docker (`uvicorn tpa_api.main:app`).
# The legacy monolith has been moved to `tpa_api.main_legacy`.
from .app import app  # noqa: F401

