from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse


def _spec_root() -> Path:
    return Path(os.environ.get("TPA_SPEC_ROOT", "/app/spec")).resolve()


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {path}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read YAML: {path}") from exc


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Not found: {path}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read JSON: {path}") from exc


app = FastAPI(title="TPA API (Scaffold)", version="0.0.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/spec/culp/process-model")
def culp_process_model() -> JSONResponse:
    root = _spec_root()
    model_path = root / "culp" / "PROCESS_MODEL.yaml"
    return JSONResponse(content=_read_yaml(model_path))


@app.get("/spec/culp/artefact-registry")
def culp_artefact_registry() -> JSONResponse:
    root = _spec_root()
    registry_path = root / "culp" / "ARTEFACT_REGISTRY.yaml"
    return JSONResponse(content=_read_yaml(registry_path))


@app.get("/spec/authorities/selected")
def selected_authorities() -> JSONResponse:
    root = _spec_root()
    selected_path = root / "authorities" / "SELECTED_AUTHORITIES.yaml"
    return JSONResponse(content=_read_yaml(selected_path))


@app.get("/spec/framing/political-framings")
def political_framings() -> JSONResponse:
    root = _spec_root()
    framings_path = root / "framing" / "POLITICAL_FRAMINGS.yaml"
    return JSONResponse(content=_read_yaml(framings_path))


@app.get("/spec/schemas")
def list_schemas() -> dict[str, list[str]]:
    root = _spec_root()
    schemas_dir = root / "schemas"
    if not schemas_dir.exists():
        raise HTTPException(status_code=404, detail="schemas directory missing in spec root")
    names = sorted(p.name for p in schemas_dir.glob("*.schema.json"))
    return {"schemas": names}


@app.get("/spec/schemas/{schema_name}")
def get_schema(schema_name: str) -> JSONResponse:
    if "/" in schema_name or ".." in schema_name:
        raise HTTPException(status_code=400, detail="Invalid schema name")
    root = _spec_root()
    schema_path = root / "schemas" / schema_name
    if not schema_path.name.endswith(".schema.json"):
        raise HTTPException(status_code=400, detail="Schema name must end with .schema.json")
    return JSONResponse(content=_read_json(schema_path))
