from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException


def _spec_root() -> Path:
    configured = Path(os.environ.get("TPA_SPEC_ROOT", "/app/spec")).resolve()
    if configured.exists():
        return configured
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {path}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to read YAML: {path}") from exc


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {path}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to read JSON: {path}") from exc
