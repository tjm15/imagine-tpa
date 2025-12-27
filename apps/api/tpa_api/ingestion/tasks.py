from __future__ import annotations

import os
from typing import Any

from celery import Celery
from kombu import Queue

from tpa_api.db import _db_fetch_one
from tpa_api.ingestion.advice_cards import enrich_advice_cards_for_documents
from tpa_api.ingestion.gis_ingest import ingest_authority_gis_layers
from tpa_api.ingestion.run_graph import run_graph_for_job_sync
from tpa_api.ingestion.spatial_interpretation import interpret_spatial_features
from tpa_api.ingestion.spatial_policy_links import link_policy_clauses_to_spatial_layers


BROKER_URL = os.environ.get("TPA_REDIS_URL") or "redis://localhost:6379/0"
celery_app = Celery("tpa_ingest", broker=BROKER_URL, backend=BROKER_URL)
celery_app.conf.task_default_queue = "ingest_cpu"
celery_app.conf.task_queues = (
    Queue("ingest_cpu"),
    Queue("ingest_vlm"),
    Queue("ingest_llm"),
    Queue("ingest_embed"),
    Queue("ingest_postprocess"),
)
celery_app.conf.task_routes = {
    "tpa_api.ingestion.tasks.process_ingest_job": {"queue": "ingest_cpu"},
    "tpa_api.ingestion.tasks.run_graph_job": {"queue": "ingest_cpu"},
    "tpa_api.ingestion.tasks.run_vlm_stage": {"queue": "ingest_vlm"},
    "tpa_api.ingestion.tasks.run_llm_stage": {"queue": "ingest_llm"},
    "tpa_api.ingestion.tasks.run_embeddings_stage": {"queue": "ingest_embed"},
    "tpa_api.ingestion.tasks.run_ingest_postprocess": {"queue": "ingest_postprocess"},
}


def _load_job_context(ingest_job_id: str) -> dict[str, Any]:
    row = _db_fetch_one(
        """
        SELECT id, ingest_batch_id, authority_id, plan_cycle_id
        FROM ingest_jobs
        WHERE id = %s::uuid
        """,
        (ingest_job_id,),
    )
    return row or {}


def _enqueue_postprocess(*, ingest_job_id: str, run_id: str | None = None) -> None:
    job = _load_job_context(ingest_job_id)
    authority_id = job.get("authority_id")
    plan_cycle_id = job.get("plan_cycle_id")
    if not authority_id:
        return
    celery_app.send_task(
        "tpa_api.ingestion.tasks.run_ingest_postprocess",
        kwargs={
            "authority_id": str(authority_id),
            "plan_cycle_id": str(plan_cycle_id) if plan_cycle_id else None,
            "run_id": run_id,
        },
    )


@celery_app.task(name="tpa_api.ingestion.tasks.process_ingest_job")
def process_ingest_job(ingest_job_id: str) -> dict[str, Any]:
    result = run_graph_for_job_sync(ingest_job_id)
    if result.get("status") == "ok":
        job = _load_job_context(ingest_job_id)
        authority_id = job.get("authority_id")
        if authority_id:
            ingest_authority_gis_layers(
                authority_id=str(authority_id),
                plan_cycle_id=str(job.get("plan_cycle_id")) if job.get("plan_cycle_id") else None,
                ingest_batch_id=str(job.get("ingest_batch_id")) if job.get("ingest_batch_id") else None,
            )
        _enqueue_postprocess(ingest_job_id=ingest_job_id, run_id=result.get("run_id"))
    return result


@celery_app.task(name="tpa_api.ingestion.tasks.run_graph_job")
def run_graph_job(ingest_job_id: str) -> dict[str, Any]:
    result = run_graph_for_job_sync(ingest_job_id)
    if result.get("status") == "ok":
        job = _load_job_context(ingest_job_id)
        authority_id = job.get("authority_id")
        if authority_id:
            ingest_authority_gis_layers(
                authority_id=str(authority_id),
                plan_cycle_id=str(job.get("plan_cycle_id")) if job.get("plan_cycle_id") else None,
                ingest_batch_id=str(job.get("ingest_batch_id")) if job.get("ingest_batch_id") else None,
            )
        _enqueue_postprocess(ingest_job_id=ingest_job_id, run_id=result.get("run_id"))
    return result


@celery_app.task(name="tpa_api.ingestion.tasks.run_vlm_stage")
def run_vlm_stage(run_id: str) -> dict[str, Any]:
    from tpa_api.ingestion.stage_runner import run_stage_for_run_sync  # noqa: PLC0415

    return run_stage_for_run_sync(run_id, "vlm")


@celery_app.task(name="tpa_api.ingestion.tasks.run_llm_stage")
def run_llm_stage(run_id: str) -> dict[str, Any]:
    from tpa_api.ingestion.stage_runner import run_stage_for_run_sync  # noqa: PLC0415

    return run_stage_for_run_sync(run_id, "llm")


@celery_app.task(name="tpa_api.ingestion.tasks.run_embeddings_stage")
def run_embeddings_stage(run_id: str) -> dict[str, Any]:
    from tpa_api.ingestion.stage_runner import run_stage_for_run_sync  # noqa: PLC0415

    return run_stage_for_run_sync(run_id, "embeddings")


@celery_app.task(name="tpa_api.ingestion.tasks.run_ingest_postprocess")
def run_ingest_postprocess(
    *,
    authority_id: str,
    plan_cycle_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    errors: list[str] = []

    try:
        advice_result = enrich_advice_cards_for_documents(
            authority_id=authority_id,
            plan_cycle_id=plan_cycle_id,
            run_id=run_id,
        )
        counts["advice_card_instances"] = int(advice_result.get("inserted") or 0)
        errors.extend([str(e) for e in advice_result.get("errors") or [] if e])
    except Exception as exc:  # noqa: BLE001
        errors.append(f"advice_card_enrichment:{exc}")

    try:
        spatial_result = interpret_spatial_features(
            authority_id=authority_id,
            run_id=run_id,
        )
        counts["spatial_feature_interpretations"] = int(spatial_result.get("interpreted") or 0)
        counts["spatial_feature_batches"] = int(spatial_result.get("batches") or 0)
        errors.extend([str(e) for e in spatial_result.get("errors") or [] if e])
    except Exception as exc:  # noqa: BLE001
        errors.append(f"spatial_interpretation:{exc}")

    try:
        link_result = link_policy_clauses_to_spatial_layers(
            authority_id=authority_id,
            plan_cycle_id=plan_cycle_id,
            run_id=run_id,
        )
        counts["spatial_policy_links"] = int(link_result.get("linked") or 0)
        errors.extend([str(e) for e in link_result.get("errors") or [] if e])
    except Exception as exc:  # noqa: BLE001
        errors.append(f"spatial_policy_links:{exc}")

    if errors:
        return {"ok": False, "counts": counts, "errors": errors}
    return {"ok": True, "counts": counts, "errors": []}
