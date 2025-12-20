from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from ..spec_io import _read_json, _read_yaml, _spec_root


def culp_process_model() -> JSONResponse:
    root = _spec_root()
    model_path = root / "culp" / "PROCESS_MODEL.yaml"
    return JSONResponse(content=_read_yaml(model_path))


def culp_artefact_registry() -> JSONResponse:
    root = _spec_root()
    registry_path = root / "culp" / "ARTEFACT_REGISTRY.yaml"
    return JSONResponse(content=_read_yaml(registry_path))


def selected_authorities() -> JSONResponse:
    root = _spec_root()
    selected_path = root / "authorities" / "SELECTED_AUTHORITIES.yaml"
    return JSONResponse(content=_read_yaml(selected_path))


def political_framings() -> JSONResponse:
    root = _spec_root()
    framings_path = root / "framing" / "POLITICAL_FRAMINGS.yaml"
    return JSONResponse(content=_read_yaml(framings_path))


def list_schemas() -> dict[str, list[str]]:
    root = _spec_root()
    schemas_dir = root / "schemas"
    if not schemas_dir.exists():
        raise HTTPException(status_code=404, detail="schemas directory missing in spec root")
    names = sorted(p.name for p in schemas_dir.glob("*.schema.json"))
    return {"schemas": names}


def get_schema(schema_name: str) -> JSONResponse:
    if "/" in schema_name or ".." in schema_name:
        raise HTTPException(status_code=400, detail="Invalid schema name")
    root = _spec_root()
    schema_path = root / "schemas" / schema_name
    if not schema_path.name.endswith(".schema.json"):
        raise HTTPException(status_code=400, detail="Schema name must end with .schema.json")
    return JSONResponse(content=_read_json(schema_path))
