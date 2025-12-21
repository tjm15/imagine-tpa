from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..db import _db_execute, _db_fetch_all, _db_fetch_one
from ..spec_io import _read_yaml, _spec_root
from ..time_utils import _utc_now


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    raise HTTPException(status_code=400, detail="Invalid date in rule pack")


def _load_process_model() -> dict[str, Any]:
    root = _spec_root()
    return _read_yaml(root / "culp" / "PROCESS_MODEL.yaml") or {}


def _load_rule_pack(path: Path) -> dict[str, Any]:
    pack = _read_yaml(path)
    if not isinstance(pack, dict):
        raise HTTPException(status_code=400, detail="Rule pack must be a YAML object")
    required = ["rule_pack_id", "name", "jurisdiction", "system", "version", "effective_from", "process_model_id"]
    missing = [k for k in required if k not in pack]
    if missing:
        raise HTTPException(status_code=400, detail=f"Rule pack missing fields: {', '.join(missing)}")
    return pack


def _upsert_rule_pack(pack: dict[str, Any]) -> tuple[str, str]:
    pack_key = str(pack["rule_pack_id"])
    now = _utc_now()
    row = _db_fetch_one("SELECT id, current_version_id FROM rule_packs WHERE pack_key = %s", (pack_key,))
    if row:
        pack_id = str(row["id"])
    else:
        pack_id = str(uuid4())
        _db_execute(
            """
            INSERT INTO rule_packs (id, pack_key, name, jurisdiction, system, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                pack_id,
                pack_key,
                str(pack["name"]),
                str(pack["jurisdiction"]),
                str(pack["system"]),
                now,
            ),
        )
    return pack_id, pack_key


def _upsert_rule_pack_version(pack_id: str, pack: dict[str, Any]) -> str:
    version = str(pack["version"])
    eff_from = _parse_date(pack["effective_from"])
    eff_to = pack.get("effective_to")
    eff_to_val = _parse_date(eff_to) if eff_to else None
    content_jsonb = json.dumps(pack, ensure_ascii=False)
    now = _utc_now()

    row = _db_fetch_one(
        "SELECT id FROM rule_pack_versions WHERE rule_pack_id = %s AND version = %s",
        (pack_id, version),
    )
    if row:
        version_id = str(row["id"])
        _db_execute(
            """
            UPDATE rule_pack_versions
            SET effective_from = %s, effective_to = %s, content_jsonb = %s::jsonb
            WHERE id = %s
            """,
            (eff_from, eff_to_val, content_jsonb, version_id),
        )
    else:
        version_id = str(uuid4())
        _db_execute(
            """
            INSERT INTO rule_pack_versions (
              id, rule_pack_id, version, effective_from, effective_to, content_jsonb, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (version_id, pack_id, version, eff_from, eff_to_val, content_jsonb, now),
        )
    _db_execute("UPDATE rule_packs SET current_version_id = %s WHERE id = %s", (version_id, pack_id))
    return version_id


def _refresh_rule_requirements(version_id: str, pack: dict[str, Any]) -> None:
    _db_execute("DELETE FROM rule_requirements WHERE rule_pack_version_id = %s", (version_id,))
    process_model = _load_process_model()
    stages = process_model.get("stages") if isinstance(process_model.get("stages"), list) else []
    now = _utc_now()
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage_id = stage.get("id")
        required = stage.get("required_artefacts", [])
        if not stage_id or not isinstance(required, list):
            continue
        for artefact_key in required:
            if not isinstance(artefact_key, str):
                continue
            requirement_key = f"{stage_id}:{artefact_key}"
            params = json.dumps({"artefact_key": artefact_key}, ensure_ascii=False)
            _db_execute(
                """
                INSERT INTO rule_requirements (
                  id, rule_pack_version_id, requirement_key, requirement_type, culp_stage_id,
                  lifecycle_state_id, params_jsonb, severity, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    str(uuid4()),
                    version_id,
                    requirement_key,
                    "artefact_required",
                    stage_id,
                    None,
                    params,
                    "hard",
                    now,
                ),
            )


def _refresh_rule_checks(version_id: str, pack: dict[str, Any]) -> None:
    _db_execute("DELETE FROM rule_checks WHERE rule_pack_version_id = %s", (version_id,))
    transitions = pack.get("transitions", [])
    if not isinstance(transitions, list):
        return
    now = _utc_now()
    for transition in transitions:
        if not isinstance(transition, dict):
            continue
        from_state = transition.get("from")
        to_state = transition.get("to")
        checks = transition.get("checks", [])
        if not from_state or not to_state or not isinstance(checks, list):
            continue
        for check in checks:
            if not isinstance(check, dict):
                continue
            check_key = str(check.get("check_key") or f"{from_state}->{to_state}")
            check_type = str(check.get("type") or "")
            if not check_type:
                continue
            params = json.dumps(check.get("params") or {}, ensure_ascii=False)
            severity = str(check.get("severity") or "hard")
            _db_execute(
                """
                INSERT INTO rule_checks (
                  id, rule_pack_version_id, check_key, check_type, from_state_id, to_state_id,
                  params_jsonb, severity, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (
                    str(uuid4()),
                    version_id,
                    check_key,
                    check_type,
                    from_state,
                    to_state,
                    params,
                    severity,
                    now,
                ),
            )


def install_rule_pack_from_file(path: Path) -> JSONResponse:
    pack = _load_rule_pack(path)
    pack_id, pack_key = _upsert_rule_pack(pack)
    version_id = _upsert_rule_pack_version(pack_id, pack)
    _refresh_rule_requirements(version_id, pack)
    _refresh_rule_checks(version_id, pack)
    return JSONResponse(
        content=jsonable_encoder(
            {
                "rule_pack_id": pack_id,
                "rule_pack_key": pack_key,
                "rule_pack_version_id": version_id,
            }
        )
    )


def install_default_rule_pack() -> JSONResponse:
    root = _spec_root()
    pack_path = root / "rulepacks" / "england_2025_11_27.yaml"
    if not pack_path.exists():
        raise HTTPException(status_code=404, detail="Default rule pack not found")
    return install_rule_pack_from_file(pack_path)


def list_rule_packs() -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, pack_key, name, jurisdiction, system, current_version_id, created_at
        FROM rule_packs
        ORDER BY created_at DESC
        """
    )
    items = [
        {
            "rule_pack_id": str(r["id"]),
            "rule_pack_key": r["pack_key"],
            "name": r["name"],
            "jurisdiction": r["jurisdiction"],
            "system": r["system"],
            "current_version_id": str(r["current_version_id"]) if r.get("current_version_id") else None,
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"rule_packs": items}))


def list_rule_pack_versions(rule_pack_key: str) -> JSONResponse:
    pack_row = _db_fetch_one("SELECT id FROM rule_packs WHERE pack_key = %s", (rule_pack_key,))
    if not pack_row:
        raise HTTPException(status_code=404, detail="Rule pack not found")
    pack_id = str(pack_row["id"])
    rows = _db_fetch_all(
        """
        SELECT id, version, effective_from, effective_to, created_at
        FROM rule_pack_versions
        WHERE rule_pack_id = %s
        ORDER BY effective_from DESC
        """,
        (pack_id,),
    )
    items = [
        {
            "rule_pack_version_id": str(r["id"]),
            "version": r["version"],
            "effective_from": r["effective_from"],
            "effective_to": r["effective_to"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"rule_pack_key": rule_pack_key, "versions": items}))


def get_rule_pack_version(rule_pack_version_id: str) -> JSONResponse:
    row = _db_fetch_one(
        """
        SELECT id, rule_pack_id, version, effective_from, effective_to, content_jsonb, created_at
        FROM rule_pack_versions
        WHERE id = %s::uuid
        """,
        (rule_pack_version_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Rule pack version not found")
    content = row.get("content_jsonb") or {}
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            content = {}
    return JSONResponse(
        content=jsonable_encoder(
            {
                "rule_pack_version_id": str(row["id"]),
                "rule_pack_id": str(row["rule_pack_id"]),
                "version": row["version"],
                "effective_from": row["effective_from"],
                "effective_to": row["effective_to"],
                "content": content,
                "created_at": row["created_at"],
            }
        )
    )
