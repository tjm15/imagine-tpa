#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


REQUIRED_PROVIDER_KEYS = [
    "BlobStoreProvider",
    "CanonicalDBProvider",
    "RetrievalProvider",
    "DocParseProvider",
    "EmbeddingProvider",
    "LLMProvider",
    "VLMProvider",
    "SegmentationProvider",
    "WorkflowProvider",
    "ObservabilityProvider",
]


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"Missing file: {path}")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to read YAML: {path}: {exc}") from exc


def _schema_filename(type_name: str) -> str:
    name = type_name.strip()
    if name.endswith("[]"):
        name = name[: -len("[]")]
    return f"{name}.schema.json"


def _validate_move_io_catalogue(*, root: Path) -> list[str]:
    errors: list[str] = []
    catalogue_path = root / "grammar" / "MOVE_IO_CATALOGUE.yaml"
    catalogue = _read_yaml(catalogue_path)
    moves = (catalogue or {}).get("moves")
    if not isinstance(moves, dict):
        return [f"{catalogue_path}: expected 'moves' mapping"]

    schemas_dir = root / "schemas"
    for move_id, contract in moves.items():
        outputs = (contract or {}).get("output") if isinstance(contract, dict) else None
        if not isinstance(outputs, list) or not outputs:
            errors.append(f"{catalogue_path}: move '{move_id}' has no outputs")
            continue
        for out in outputs:
            if not isinstance(out, str) or not out.strip():
                errors.append(f"{catalogue_path}: move '{move_id}' has invalid output entry: {out!r}")
                continue
            schema_name = _schema_filename(out)
            schema_path = schemas_dir / schema_name
            if not schema_path.exists():
                errors.append(f"{catalogue_path}: move '{move_id}' output '{out}' missing schema: {schema_path}")
    return errors


def _validate_capability_registry(*, root: Path) -> list[str]:
    errors: list[str] = []
    capabilities_path = root / "capabilities" / "CAPABILITIES_CATALOGUE.yaml"
    registry_path = root / "tools" / "CAPABILITY_MODULE_REGISTRY.yaml"
    catalogue = _read_yaml(capabilities_path)
    registry = _read_yaml(registry_path)

    modules = (registry or {}).get("modules")
    if not isinstance(modules, list):
        return [f"{registry_path}: expected 'modules' list"]
    module_ids = {m.get("id") for m in modules if isinstance(m, dict)}

    caps = (catalogue or {}).get("capabilities")
    if not isinstance(caps, list):
        return [f"{capabilities_path}: expected 'capabilities' list"]

    for cap in caps:
        if not isinstance(cap, dict):
            errors.append(f"{capabilities_path}: invalid capability entry: {cap!r}")
            continue
        cap_id = cap.get("id")
        powered_by = cap.get("powered_by")
        if not powered_by:
            errors.append(f"{capabilities_path}: capability '{cap_id}' missing powered_by")
            continue
        if powered_by not in module_ids:
            errors.append(
                f"{capabilities_path}: capability '{cap_id}' powered_by '{powered_by}' not found in {registry_path}"
            )
    return errors


def _validate_profiles(*, root: Path) -> list[str]:
    errors: list[str] = []
    profiles_dir = root / "profiles"
    for profile_name in ("oss.yaml", "azure.yaml"):
        path = profiles_dir / profile_name
        profile = _read_yaml(path)
        profile_id = (profile or {}).get("profile")
        providers = (profile or {}).get("providers")

        if profile_id not in {"oss", "azure"}:
            errors.append(f"{path}: profile must be 'oss' or 'azure' (got {profile_id!r})")
            continue
        if not isinstance(providers, dict):
            errors.append(f"{path}: expected 'providers' mapping")
            continue

        missing = [k for k in REQUIRED_PROVIDER_KEYS if k not in providers]
        if missing:
            errors.append(f"{path}: missing required providers: {', '.join(missing)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the TPA contract/spec pack (file-level checks).")
    parser.add_argument("--root", default=".", help="Repo root (default: current directory)")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    failures: list[str] = []
    failures.extend(_validate_move_io_catalogue(root=root))
    failures.extend(_validate_capability_registry(root=root))
    failures.extend(_validate_profiles(root=root))

    if failures:
        print("Spec pack validation: FAILED\n", file=sys.stderr)
        for f in failures:
            print(f"- {f}", file=sys.stderr)
        return 2

    print("Spec pack validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

