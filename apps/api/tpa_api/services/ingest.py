from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..api_utils import validate_uuid_or_400 as _validate_uuid_or_400
from ..audit import _audit_event
from ..db import _db_execute, _db_execute_returning, _db_fetch_all, _db_fetch_one
from ..spec_io import _read_json, _read_yaml
from ..time_utils import _utc_now


def _authority_packs_root() -> Path:
    return Path(os.environ.get("TPA_AUTHORITY_PACKS_ROOT", "/authority_packs")).resolve()


def _load_authority_pack_manifest(authority_id: str) -> dict[str, Any]:
    root = _authority_packs_root() / authority_id
    json_path = root / "manifest.json"
    yaml_path = root / "manifest.yaml"
    if json_path.exists():
        return _read_json(json_path)
    if yaml_path.exists():
        return _read_yaml(yaml_path)
    raise HTTPException(status_code=404, detail=f"Authority pack manifest not found for '{authority_id}'")


def _is_http_url(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
    except Exception:  # noqa: BLE001
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return cleaned or "document"


def _derive_filename_for_url(url: str, *, content_type: str | None = None) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name or "document"
    name = _sanitize_filename(name)
    stem = Path(name).stem or "document"
    suffix = Path(name).suffix
    if not suffix and content_type:
        suffix = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ""
    if not suffix:
        suffix = ".pdf"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{stem}-{digest}{suffix}"


def _web_automation_ingest_url(
    *,
    url: str,
    ingest_batch_id: str,
    run_id: str | None = None,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    base_url = os.environ.get("TPA_WEB_AUTOMATION_BASE_URL")
    if not base_url:
        return {"ok": False, "error": "web_automation_unconfigured"}

    tool_run_id = str(uuid4())
    started = _utc_now()
    tool_run_inserted = False
    try:
        _db_execute(
            """
            INSERT INTO tool_runs (
              id, ingest_batch_id, run_id, tool_name, inputs_logged, outputs_logged, status,
              started_at, ended_at, confidence_hint, uncertainty_note
            )
            VALUES (%s, %s::uuid, %s::uuid, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, %s, %s)
            """,
            (
                tool_run_id,
                ingest_batch_id,
                run_id,
                "web_ingest",
                json.dumps({"url": url, "base_url": base_url}, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                "running",
                started,
                "low",
                "Web capture requested; awaiting response.",
            ),
        )
        tool_run_inserted = True
    except Exception:  # noqa: BLE001
        tool_run_inserted = False

    payload = {
        "url": url,
        "screenshot": False,
    }

    try:
        with httpx.Client(timeout=None) as client:
            resp = client.post(base_url.rstrip("/") + "/ingest", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        if tool_run_inserted:
            _db_execute(
                """
                UPDATE tool_runs
                SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                    confidence_hint = %s, uncertainty_note = %s
                WHERE id = %s::uuid
                """,
                (
                    "error",
                    json.dumps({"error": str(exc)}, ensure_ascii=False),
                    _utc_now(),
                    "low",
                    "Web capture failed; check web automation service connectivity.",
                    tool_run_id,
                ),
            )
        return {"ok": False, "error": f"web_ingest_failed: {exc}", "tool_run_id": tool_run_id}

    content_type = data.get("content_type")
    content_type_norm = str(content_type or "").lower()
    if "pdf" not in content_type_norm:
        if tool_run_inserted:
            _db_execute(
                """
                UPDATE tool_runs
                SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                    confidence_hint = %s, uncertainty_note = %s
                WHERE id = %s::uuid
                """,
                (
                    "partial",
                    json.dumps(
                        {
                            "content_type": content_type,
                            "final_url": data.get("final_url"),
                            "http_status": data.get("http_status"),
                        },
                        ensure_ascii=False,
                    ),
                    _utc_now(),
                    "low",
                    "Web capture succeeded but did not return a PDF payload.",
                    tool_run_id,
                ),
            )
        return {
            "ok": False,
            "error": f"unsupported_content_type:{content_type}",
            "tool_run_id": tool_run_id,
        }

    payload_b64 = data.get("content_base64")
    if not isinstance(payload_b64, str) or not payload_b64:
        if tool_run_inserted:
            _db_execute(
                """
                UPDATE tool_runs
                SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                    confidence_hint = %s, uncertainty_note = %s
                WHERE id = %s::uuid
                """,
                (
                    "error",
                    json.dumps({"error": "missing_content_base64"}, ensure_ascii=False),
                    _utc_now(),
                    "low",
                    "Web capture returned an empty payload.",
                    tool_run_id,
                ),
            )
        return {"ok": False, "error": "missing_content_base64", "tool_run_id": tool_run_id}

    try:
        data_bytes = base64.b64decode(payload_b64)
    except Exception as exc:  # noqa: BLE001
        if tool_run_inserted:
            _db_execute(
                """
                UPDATE tool_runs
                SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                    confidence_hint = %s, uncertainty_note = %s
                WHERE id = %s::uuid
                """,
                (
                    "error",
                    json.dumps({"error": str(exc)}, ensure_ascii=False),
                    _utc_now(),
                    "low",
                    "Web capture payload could not be decoded.",
                    tool_run_id,
                ),
            )
        return {"ok": False, "error": f"decode_failed:{exc}", "tool_run_id": tool_run_id}

    if content_type_norm == "pdf":
        content_type = "application/pdf"

    outputs = {
        "content_type": content_type,
        "content_bytes": len(data_bytes),
        "final_url": data.get("final_url"),
        "requested_url": data.get("requested_url"),
        "http_status": data.get("http_status"),
        "limitations_text": data.get("limitations_text"),
        "filename": data.get("filename"),
    }
    if tool_run_inserted:
        _db_execute(
            """
            UPDATE tool_runs
            SET status = %s, outputs_logged = %s::jsonb, ended_at = %s,
                confidence_hint = %s, uncertainty_note = %s
            WHERE id = %s::uuid
            """,
            (
                "success",
                json.dumps(outputs, ensure_ascii=False),
                _utc_now(),
                "medium",
                "Web capture delivered a PDF payload; treat as evidence artefact.",
                tool_run_id,
            ),
        )

    return {
        "ok": True,
        "bytes": data_bytes,
        "content_type": content_type,
        "final_url": data.get("final_url") or url,
        "requested_url": data.get("requested_url") or url,
        "filename": data.get("filename"),
        "limitations_text": data.get("limitations_text"),
        "tool_run_id": tool_run_id,
    }


def _normalize_authority_pack_documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    raw = manifest.get("documents", [])
    if raw is None:
        return []
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        out: list[dict[str, Any]] = []
        for item in raw:
            if _is_http_url(item):
                title = Path(urlparse(item).path).stem or "document"
                out.append({"file_path": None, "source_url": item, "title": title, "source": "web_automation"})
            else:
                out.append({"file_path": item, "title": Path(item).stem, "source": "authority_pack"})
        return out
    if isinstance(raw, list) and all(isinstance(x, dict) for x in raw):
        out: list[dict[str, Any]] = []
        for d in raw:
            fp = d.get("file_path") or d.get("path") or d.get("file")
            source_url = d.get("url") or d.get("source_url") or d.get("href")
            if not fp and not source_url:
                continue
            title_hint = d.get("title")
            if not title_hint:
                if source_url:
                    title_hint = Path(urlparse(str(source_url)).path).stem or "document"
                if not title_hint and fp:
                    title_hint = Path(str(fp)).stem
            out.append(
                {
                    "file_path": fp,
                    "source_url": source_url,
                    "title": title_hint,
                    "document_type": d.get("type") or d.get("document_type"),
                    "source": d.get("source") or ("web_automation" if source_url else "authority_pack"),
                    "published_date": d.get("published_date") or d.get("date"),
                }
            )
        return out
    return []


class PlanCycleInline(BaseModel):
    plan_name: str
    status: str
    weight_hint: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthorityPackIngestRequest(BaseModel):
    source_system: str = Field(default="authority_pack")
    plan_cycle_id: str | None = None
    plan_cycle: PlanCycleInline | None = None
    notes: str | None = None


def _prepare_authority_pack_ingest(
    *,
    authority_id: str,
    body: AuthorityPackIngestRequest,
    manifest: dict[str, Any],
    document_count: int,
) -> tuple[dict[str, Any], str, str, str, datetime]:
    """
    Creates (or resolves) a plan cycle + creates an ingest_batch envelope.

    Returns: (plan_cycle_row, plan_cycle_id, ingest_batch_id, tool_run_id, started_at)
    """
    try:
        plan_cycle_row: dict[str, Any] | None = None
        plan_cycle_id = body.plan_cycle_id
        if plan_cycle_id:
            plan_cycle_id = _validate_uuid_or_400(plan_cycle_id, field_name="plan_cycle_id")
            plan_cycle_row = _db_fetch_one(
                """
                SELECT id, authority_id, plan_name, status, weight_hint, effective_from, effective_to
                FROM plan_cycles
                WHERE id = %s::uuid
                """,
                (plan_cycle_id,),
            )
            if not plan_cycle_row:
                raise HTTPException(status_code=404, detail="plan_cycle_id not found")
            if plan_cycle_row["authority_id"] != authority_id:
                raise HTTPException(status_code=400, detail="plan_cycle_id does not belong to this authority_id")
        else:
            if body.plan_cycle is None:
                raise HTTPException(
                    status_code=400,
                    detail="Provide either plan_cycle_id or plan_cycle {plan_name,status,...} to make authority versioning explicit.",
                )
            now = _utc_now()
            plan_cycle_row = _db_execute_returning(
                """
                INSERT INTO plan_cycles (
                  id, authority_id, plan_name, status, weight_hint, effective_from, effective_to,
                  metadata_jsonb, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING id, authority_id, plan_name, status, weight_hint, effective_from, effective_to
                """,
                (
                    str(uuid4()),
                    authority_id,
                    body.plan_cycle.plan_name,
                    body.plan_cycle.status,
                    body.plan_cycle.weight_hint,
                    body.plan_cycle.effective_from,
                    body.plan_cycle.effective_to,
                    json.dumps(body.plan_cycle.metadata, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            plan_cycle_id = str(plan_cycle_row["id"])
            _audit_event(
                event_type="plan_cycle_created",
                actor_type="system",
                payload={"plan_cycle_id": plan_cycle_id, "authority_id": authority_id, "status": plan_cycle_row["status"]},
            )

        if not isinstance(plan_cycle_row, dict):
            raise HTTPException(status_code=500, detail="Failed to resolve plan cycle")

        ingest_batch_id = str(uuid4())
        tool_run_id = str(uuid4())
        started_at = _utc_now()

        _db_execute(
            """
            INSERT INTO ingest_batches (
              id, source_system, authority_id, plan_cycle_id,
              started_at, completed_at, status, notes,
              inputs_jsonb, outputs_jsonb
            )
            VALUES (%s, %s, %s, %s::uuid, %s, NULL, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                ingest_batch_id,
                body.source_system,
                authority_id,
                plan_cycle_id,
                started_at,
                "running",
                body.notes,
                json.dumps(
                    {
                        "authority_pack_id": manifest.get("id"),
                        "authority_pack_name": manifest.get("name"),
                        "document_count": int(document_count),
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"counts": {}, "errors": [], "progress": {"phase": "starting"}}, ensure_ascii=False),
            ),
        )

        return plan_cycle_row, str(plan_cycle_id), ingest_batch_id, tool_run_id, started_at
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "relation" in msg and any(t in msg for t in ["plan_cycles", "ingest_batches", "tool_runs", "documents", "chunks"]):
            raise HTTPException(
                status_code=500,
                detail=(
                    "Database schema appears out of date (missing expected tables). "
                    "If you pulled new repo changes after the first boot, reset the Postgres volume so init SQL runs: "
                    "`docker compose -f docker/compose.oss.yml down` then `docker volume rm tpa-oss_tpa_db_data` "
                    "then `docker compose -f docker/compose.oss.yml up -d --build`."
                ),
            ) from exc
        raise HTTPException(status_code=500, detail=f"Ingest setup failed: {msg}") from exc


def _update_ingest_batch_progress(
    *,
    ingest_batch_id: str,
    status: str,
    counts: dict[str, int],
    errors: list[str],
    document_ids: list[str],
    plan_cycle_id: str,
    progress: dict[str, Any],
) -> None:
    payload = {
        "counts": counts,
        "errors": errors[:50],
        "document_ids": document_ids[:200],
        "plan_cycle_id": plan_cycle_id,
        "progress": progress,
    }
    try:
        _db_execute(
            "UPDATE ingest_batches SET status = %s, outputs_jsonb = %s::jsonb WHERE id = %s::uuid",
            (status, json.dumps(payload, ensure_ascii=False), ingest_batch_id),
        )
    except Exception:  # noqa: BLE001
        pass


def _create_ingest_job(
    *,
    authority_id: str,
    plan_cycle_id: str,
    ingest_batch_id: str,
    job_type: str,
    inputs: dict[str, Any],
) -> str:
    job_id = str(uuid4())
    _db_execute(
        """
        INSERT INTO ingest_jobs (
          id, ingest_batch_id, authority_id, plan_cycle_id, job_type, status,
          inputs_jsonb, outputs_jsonb, created_at
        )
        VALUES (%s, %s::uuid, %s, %s::uuid, %s, %s, %s::jsonb, %s::jsonb, %s)
        """,
        (
            job_id,
            ingest_batch_id,
            authority_id,
            plan_cycle_id,
            job_type,
            "pending",
            json.dumps(inputs, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
            _utc_now(),
        ),
    )
    return job_id


def _enqueue_ingest_job(job_id: str) -> tuple[bool, str | None]:
    try:
        from ..ingest_worker import celery_app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return False, f"celery_import_failed:{exc}"
    try:
        celery_app.send_task("tpa_api.ingest_worker.process_ingest_job", args=[job_id])
    except Exception as exc:  # noqa: BLE001
        return False, f"celery_enqueue_failed:{exc}"
    return True, None


def start_ingest_authority_pack(authority_id: str, body: AuthorityPackIngestRequest | None = None) -> JSONResponse:
    body = body or AuthorityPackIngestRequest()

    pack_dir = _authority_packs_root() / authority_id
    if not pack_dir.exists():
        raise HTTPException(status_code=404, detail=f"Authority pack not found: {authority_id}")

    manifest = _load_authority_pack_manifest(authority_id)
    documents = _normalize_authority_pack_documents(manifest)
    if not documents:
        raise HTTPException(status_code=400, detail=f"No documents listed in authority pack manifest for '{authority_id}'")

    # If a run is already in-flight for this authority+cycle, return it.
    if body.plan_cycle_id:
        body.plan_cycle_id = _validate_uuid_or_400(body.plan_cycle_id, field_name="plan_cycle_id")
        existing = _db_fetch_one(
            """
            SELECT id
            FROM ingest_batches
            WHERE authority_id = %s
              AND plan_cycle_id = %s::uuid
              AND status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (authority_id, body.plan_cycle_id),
        )
        if existing:
            ingest_batch_id = str(existing["id"])
            return JSONResponse(
                status_code=202,
                content=jsonable_encoder(
                    {
                        "authority_id": authority_id,
                        "plan_cycle_id": body.plan_cycle_id,
                        "ingest_batch_id": ingest_batch_id,
                        "status": "running",
                        "message": "Ingest already running for this plan cycle.",
                    }
                ),
            )

    plan_cycle_row, plan_cycle_id, ingest_batch_id, tool_run_id, started_at = _prepare_authority_pack_ingest(
        authority_id=authority_id,
        body=body,
        manifest=manifest,
        document_count=len(documents),
    )
    ingest_job_id = _create_ingest_job(
        authority_id=authority_id,
        plan_cycle_id=plan_cycle_id,
        ingest_batch_id=ingest_batch_id,
        job_type="authority_pack",
        inputs={
            "authority_id": authority_id,
            "plan_cycle_id": plan_cycle_id,
            "pack_dir": str(pack_dir),
            "documents": documents,
            "manifest": {"id": manifest.get("id"), "name": manifest.get("name")},
        },
    )
    enqueued, enqueue_error = _enqueue_ingest_job(ingest_job_id)
    if not enqueued:
        raise HTTPException(status_code=500, detail=f"Failed to enqueue ingest job: {enqueue_error}")

    _audit_event(
        event_type="authority_pack_ingest_queued",
        actor_type="system",
        payload={
            "authority_id": authority_id,
            "plan_cycle_id": plan_cycle_id,
            "ingest_batch_id": ingest_batch_id,
            "ingest_job_id": ingest_job_id,
        },
    )

    return JSONResponse(
        status_code=202,
        content=jsonable_encoder(
            {
                "authority_id": authority_id,
                "plan_cycle_id": plan_cycle_id,
                "ingest_batch_id": ingest_batch_id,
                "ingest_job_id": ingest_job_id,
                "tool_run_id": tool_run_id,
                "status": "queued",
                "message": "Ingest job queued.",
            }
        ),
    )


def ingest_authority_pack(authority_id: str, body: AuthorityPackIngestRequest | None = None) -> JSONResponse:
    body = body or AuthorityPackIngestRequest()
    return start_ingest_authority_pack(authority_id, body)


def list_ingest_batches(
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    limit: int = 25,
) -> JSONResponse:
    limit = max(1, min(int(limit), 200))
    where: list[str] = []
    params: list[Any] = []
    if authority_id:
        where.append("authority_id = %s")
        params.append(authority_id)
    if plan_cycle_id:
        where.append("plan_cycle_id = %s::uuid")
        params.append(plan_cycle_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = _db_fetch_all(
        f"""
        SELECT
          id, source_system, authority_id, plan_cycle_id,
          started_at, completed_at, status, notes, inputs_jsonb, outputs_jsonb
        FROM ingest_batches
        {where_sql}
        ORDER BY started_at DESC
        LIMIT %s
        """,
        tuple(params + [limit]),
    )
    items = [
        {
            "ingest_batch_id": str(r["id"]),
            "source_system": r["source_system"],
            "authority_id": r["authority_id"],
            "plan_cycle_id": str(r["plan_cycle_id"]) if r["plan_cycle_id"] else None,
            "started_at": r["started_at"],
            "completed_at": r["completed_at"],
            "status": r["status"],
            "notes": r["notes"],
            "inputs": r["inputs_jsonb"] or {},
            "outputs": r["outputs_jsonb"] or {},
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"ingest_batches": items}))


def list_ingest_jobs(
    authority_id: str | None = None,
    plan_cycle_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> JSONResponse:
    limit = max(1, min(int(limit), 200))
    where: list[str] = []
    params: list[Any] = []
    if authority_id:
        where.append("authority_id = %s")
        params.append(authority_id)
    if plan_cycle_id:
        where.append("plan_cycle_id = %s::uuid")
        params.append(plan_cycle_id)
    if status:
        where.append("status = %s")
        params.append(status)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = _db_fetch_all(
        f"""
        SELECT id, ingest_batch_id, authority_id, plan_cycle_id, job_type, status,
               inputs_jsonb, outputs_jsonb, created_at, started_at, completed_at, error_text
        FROM ingest_jobs
        {where_sql}
        ORDER BY created_at DESC
        LIMIT %s
        """,
        tuple(params + [limit]),
    )
    jobs = [
        {
            "ingest_job_id": str(r["id"]),
            "ingest_batch_id": str(r["ingest_batch_id"]) if r.get("ingest_batch_id") else None,
            "authority_id": r.get("authority_id"),
            "plan_cycle_id": str(r["plan_cycle_id"]) if r.get("plan_cycle_id") else None,
            "job_type": r.get("job_type"),
            "status": r.get("status"),
            "inputs": r.get("inputs_jsonb") or {},
            "outputs": r.get("outputs_jsonb") or {},
            "created_at": r.get("created_at"),
            "started_at": r.get("started_at"),
            "completed_at": r.get("completed_at"),
            "error_text": r.get("error_text"),
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder({"ingest_jobs": jobs}))


def get_ingest_job(ingest_job_id: str) -> JSONResponse:
    row = _db_fetch_one(
        """
        SELECT id, ingest_batch_id, authority_id, plan_cycle_id, job_type, status,
               inputs_jsonb, outputs_jsonb, created_at, started_at, completed_at, error_text
        FROM ingest_jobs
        WHERE id = %s::uuid
        """,
        (ingest_job_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Ingest job not found")

    return JSONResponse(
        content=jsonable_encoder(
            {
                "ingest_job": {
                    "ingest_job_id": str(row["id"]),
                    "ingest_batch_id": str(row["ingest_batch_id"]) if row.get("ingest_batch_id") else None,
                    "authority_id": row.get("authority_id"),
                    "plan_cycle_id": str(row["plan_cycle_id"]) if row.get("plan_cycle_id") else None,
                    "job_type": row.get("job_type"),
                    "status": row.get("status"),
                    "inputs": row.get("inputs_jsonb") or {},
                    "outputs": row.get("outputs_jsonb") or {},
                    "created_at": row.get("created_at"),
                    "started_at": row.get("started_at"),
                    "completed_at": row.get("completed_at"),
                    "error_text": row.get("error_text"),
                }
            }
        )
    )


def get_ingest_batch(ingest_batch_id: str) -> JSONResponse:
    row = _db_fetch_one(
        """
        SELECT
          id, source_system, authority_id, plan_cycle_id,
          started_at, completed_at, status, notes, inputs_jsonb, outputs_jsonb
        FROM ingest_batches
        WHERE id = %s::uuid
        """,
        (ingest_batch_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Ingest batch not found")

    tool_runs = _db_fetch_all(
        """
        SELECT id, tool_name, status, started_at, ended_at, confidence_hint, uncertainty_note
        FROM tool_runs
        WHERE ingest_batch_id = %s::uuid
        ORDER BY started_at ASC
        """,
        (ingest_batch_id,),
    )

    return JSONResponse(
        content=jsonable_encoder(
            {
                "ingest_batch": {
                    "ingest_batch_id": str(row["id"]),
                    "source_system": row["source_system"],
                    "authority_id": row["authority_id"],
                    "plan_cycle_id": str(row["plan_cycle_id"]) if row["plan_cycle_id"] else None,
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "status": row["status"],
                    "notes": row["notes"],
                    "inputs": row["inputs_jsonb"] or {},
                    "outputs": row["outputs_jsonb"] or {},
                    "tool_runs": [
                        {
                            "tool_run_id": str(t["id"]),
                            "tool_name": t["tool_name"],
                            "status": t["status"],
                            "started_at": t["started_at"],
                            "ended_at": t["ended_at"],
                            "confidence_hint": t["confidence_hint"],
                            "uncertainty_note": t["uncertainty_note"],
                        }
                        for t in tool_runs
                    ],
                }
            }
        )
    )


def get_document_coverage(document_id: str, run_id: str | None = None, alias: str | None = None) -> JSONResponse:
    document_id = _validate_uuid_or_400(document_id, field_name="document_id")
    if run_id:
        run_id = _validate_uuid_or_400(run_id, field_name="run_id")

    doc_row = _db_fetch_one(
        """
        SELECT id, authority_id, plan_cycle_id, metadata, raw_blob_path, raw_sha256, raw_bytes, raw_source_uri
        FROM documents
        WHERE id = %s::uuid
        """,
        (document_id,),
    )
    if not doc_row:
        raise HTTPException(status_code=404, detail="Document not found")

    if not run_id and alias:
        alias_row = _db_fetch_one(
            """
            SELECT run_id
            FROM ingest_run_aliases
            WHERE scope_type = %s AND scope_key = %s AND alias = %s
            """,
            ("document", document_id, alias),
        )
        if alias_row and alias_row.get("run_id"):
            run_id = str(alias_row["run_id"])

    if not run_id and alias:
        scope_key = str(doc_row.get("plan_cycle_id") or doc_row.get("authority_id") or "")
        scope_type = "plan_cycle" if doc_row.get("plan_cycle_id") else "authority"
        if scope_key:
            alias_row = _db_fetch_one(
                """
                SELECT run_id
                FROM ingest_run_aliases
                WHERE scope_type = %s AND scope_key = %s AND alias = %s
                """,
                (scope_type, scope_key, alias),
            )
            if alias_row and alias_row.get("run_id"):
                run_id = str(alias_row["run_id"])

    if not run_id:
        bundle_row = _db_fetch_one(
            """
            SELECT run_id
            FROM parse_bundles
            WHERE document_id = %s::uuid
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (document_id,),
        )
        if bundle_row and bundle_row.get("run_id"):
            run_id = str(bundle_row["run_id"])

    if not run_id:
        return JSONResponse(status_code=404, content=jsonable_encoder({"document_id": document_id, "error": "run_id_unavailable"}))

    bundle_meta = _db_fetch_one(
        """
        SELECT id, schema_version, metadata_jsonb, created_at
        FROM parse_bundles
        WHERE document_id = %s::uuid AND run_id = %s::uuid
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (document_id, run_id),
    )

    run_row = _db_fetch_one(
        """
        SELECT id, status, pipeline_version, started_at, completed_at
        FROM ingest_runs
        WHERE id = %s::uuid
        """,
        (run_id,),
    )

    def _count(sql: str, params: tuple[Any, ...]) -> int:
        row = _db_fetch_one(sql, params)
        if not row:
            return 0
        return int(row.get("count") or 0)

    counts = {
        "pages": _count(
            "SELECT COUNT(*) AS count FROM pages WHERE document_id = %s::uuid AND run_id = %s::uuid",
            (document_id, run_id),
        ),
        "layout_blocks": _count(
            "SELECT COUNT(*) AS count FROM layout_blocks WHERE document_id = %s::uuid AND run_id = %s::uuid",
            (document_id, run_id),
        ),
        "tables": _count(
            "SELECT COUNT(*) AS count FROM document_tables WHERE document_id = %s::uuid AND run_id = %s::uuid",
            (document_id, run_id),
        ),
        "vector_paths": _count(
            "SELECT COUNT(*) AS count FROM vector_paths WHERE document_id = %s::uuid AND run_id = %s::uuid",
            (document_id, run_id),
        ),
        "chunks": _count(
            "SELECT COUNT(*) AS count FROM chunks WHERE document_id = %s::uuid AND run_id = %s::uuid",
            (document_id, run_id),
        ),
        "visual_assets": _count(
            "SELECT COUNT(*) AS count FROM visual_assets WHERE document_id = %s::uuid AND run_id = %s::uuid",
            (document_id, run_id),
        ),
        "segmentation_masks": _count(
            """
            SELECT COUNT(*) AS count
            FROM segmentation_masks sm
            JOIN visual_assets va ON va.id = sm.visual_asset_id
            WHERE va.document_id = %s::uuid AND sm.run_id = %s::uuid
            """,
            (document_id, run_id),
        ),
        "visual_asset_regions": _count(
            """
            SELECT COUNT(*) AS count
            FROM visual_asset_regions vr
            JOIN visual_assets va ON va.id = vr.visual_asset_id
            WHERE va.document_id = %s::uuid AND vr.run_id = %s::uuid
            """,
            (document_id, run_id),
        ),
        "visual_asset_links": _count(
            """
            SELECT COUNT(*) AS count
            FROM visual_asset_links vl
            JOIN visual_assets va ON va.id = vl.visual_asset_id
            WHERE va.document_id = %s::uuid AND vl.run_id = %s::uuid
            """,
            (document_id, run_id),
        ),
        "policy_sections": _count(
            "SELECT COUNT(*) AS count FROM policy_sections WHERE document_id = %s::uuid AND run_id = %s::uuid",
            (document_id, run_id),
        ),
        "policy_clauses": _count(
            """
            SELECT COUNT(*) AS count
            FROM policy_clauses pc
            JOIN policy_sections ps ON ps.id = pc.policy_section_id
            WHERE ps.document_id = %s::uuid AND pc.run_id = %s::uuid
            """,
            (document_id, run_id),
        ),
        "definitions": _count(
            """
            SELECT COUNT(*) AS count
            FROM policy_definitions pd
            JOIN policy_sections ps ON ps.id = pd.policy_section_id
            WHERE ps.document_id = %s::uuid AND pd.run_id = %s::uuid
            """,
            (document_id, run_id),
        ),
        "targets": _count(
            """
            SELECT COUNT(*) AS count
            FROM policy_targets pt
            JOIN policy_sections ps ON ps.id = pt.policy_section_id
            WHERE ps.document_id = %s::uuid AND pt.run_id = %s::uuid
            """,
            (document_id, run_id),
        ),
        "monitoring": _count(
            """
            SELECT COUNT(*) AS count
            FROM policy_monitoring_hooks pm
            JOIN policy_sections ps ON ps.id = pm.policy_section_id
            WHERE ps.document_id = %s::uuid AND pm.run_id = %s::uuid
            """,
            (document_id, run_id),
        ),
        "unit_embeddings_chunk": _count(
            """
            SELECT COUNT(*) AS count
            FROM unit_embeddings ue
            JOIN chunks c ON c.id = ue.unit_id
            WHERE ue.unit_type = 'chunk' AND c.document_id = %s::uuid AND ue.run_id = %s::uuid
            """,
            (document_id, run_id),
        ),
        "unit_embeddings_policy_section": _count(
            """
            SELECT COUNT(*) AS count
            FROM unit_embeddings ue
            JOIN policy_sections ps ON ps.id = ue.unit_id
            WHERE ue.unit_type = 'policy_section' AND ps.document_id = %s::uuid AND ue.run_id = %s::uuid
            """,
            (document_id, run_id),
        ),
        "unit_embeddings_policy_clause": _count(
            """
            SELECT COUNT(*) AS count
            FROM unit_embeddings ue
            JOIN policy_clauses pc ON pc.id = ue.unit_id
            JOIN policy_sections ps ON ps.id = pc.policy_section_id
            WHERE ue.unit_type = 'policy_clause' AND ps.document_id = %s::uuid AND ue.run_id = %s::uuid
            """,
            (document_id, run_id),
        ),
        "unit_embeddings_visual": _count(
            """
            SELECT COUNT(*) AS count
            FROM unit_embeddings ue
            JOIN visual_assets va ON va.id = ue.unit_id
            WHERE ue.unit_type = 'visual_asset' AND va.document_id = %s::uuid AND ue.run_id = %s::uuid
            """,
            (document_id, run_id),
        ),
    }

    assertions = [
        {
            "check": "raw_artifact",
            "ok": bool(doc_row.get("raw_blob_path") and doc_row.get("raw_sha256")),
            "detail": "Raw PDF persisted with hash.",
        },
        {
            "check": "layout_blocks_present",
            "ok": counts["layout_blocks"] > 0,
            "detail": "Layout blocks extracted.",
        },
        {
            "check": "policy_structure_present",
            "ok": counts["policy_sections"] > 0 and counts["policy_clauses"] > 0,
            "detail": "Policy sections and clauses extracted.",
        },
        {
            "check": "embeddings_present",
            "ok": counts["unit_embeddings_chunk"] > 0,
            "detail": "Text embeddings exist.",
        },
    ]

    return JSONResponse(
        content=jsonable_encoder(
            {
                "document_id": document_id,
                "run_id": run_id,
                "authority_id": doc_row.get("authority_id"),
                "plan_cycle_id": str(doc_row.get("plan_cycle_id")) if doc_row.get("plan_cycle_id") else None,
                "document_metadata": doc_row.get("metadata") or {},
                "raw": {
                    "raw_blob_path": doc_row.get("raw_blob_path"),
                    "raw_sha256": doc_row.get("raw_sha256"),
                    "raw_bytes": doc_row.get("raw_bytes"),
                    "raw_source_uri": doc_row.get("raw_source_uri"),
                },
                "parse_bundle": {
                    "parse_bundle_id": str(bundle_meta["id"]) if bundle_meta else None,
                    "schema_version": bundle_meta.get("schema_version") if bundle_meta else None,
                    "created_at": bundle_meta.get("created_at") if bundle_meta else None,
                    "parse_flags": (bundle_meta.get("metadata_jsonb") or {}).get("parse_flags") if bundle_meta else [],
                    "tables_unimplemented": bool((bundle_meta.get("metadata_jsonb") or {}).get("tables_unimplemented"))
                    if bundle_meta
                    else False,
                },
                "run": {
                    "status": run_row.get("status") if run_row else None,
                    "pipeline_version": run_row.get("pipeline_version") if run_row else None,
                    "started_at": run_row.get("started_at") if run_row else None,
                    "completed_at": run_row.get("completed_at") if run_row else None,
                },
                "counts": counts,
                "assertions": assertions,
            }
        )
    )
