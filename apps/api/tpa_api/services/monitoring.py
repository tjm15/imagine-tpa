from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..db import _db_execute_returning, _db_fetch_all


class MonitoringEventCreate(BaseModel):
    authority_id: str
    event_type: str
    event_date: str
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class MonitoringTimeseriesCreate(BaseModel):
    authority_id: str
    metric_id: str
    period: str
    value: float | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


def create_monitoring_event(body: MonitoringEventCreate) -> JSONResponse:
    row = _db_execute_returning(
        """
        INSERT INTO monitoring_events (
          id, authority_id, event_type, event_date, payload_jsonb, provenance
        )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
        RETURNING id, authority_id, event_type, event_date, payload_jsonb, provenance
        """,
        (
            str(uuid4()),
            body.authority_id,
            body.event_type,
            body.event_date,
            json.dumps(body.payload, ensure_ascii=False),
            json.dumps(body.provenance, ensure_ascii=False),
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_event(row)))


def list_monitoring_events(authority_id: str) -> JSONResponse:
    rows = _db_fetch_all(
        """
        SELECT id, authority_id, event_type, event_date, payload_jsonb, provenance
        FROM monitoring_events
        WHERE authority_id = %s
        ORDER BY event_date DESC
        """,
        (authority_id,),
    )
    items = [_row_to_event(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"monitoring_events": items}))


def create_monitoring_timeseries(body: MonitoringTimeseriesCreate) -> JSONResponse:
    row = _db_execute_returning(
        """
        INSERT INTO monitoring_timeseries (
          id, authority_id, metric_id, period, value, provenance
        )
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id, authority_id, metric_id, period, value, provenance
        """,
        (
            str(uuid4()),
            body.authority_id,
            body.metric_id,
            body.period,
            body.value,
            json.dumps(body.provenance, ensure_ascii=False),
        ),
    )
    return JSONResponse(content=jsonable_encoder(_row_to_timeseries(row)))


def list_monitoring_timeseries(authority_id: str, metric_id: str | None = None) -> JSONResponse:
    params: list[Any] = [authority_id]
    clause = ""
    if metric_id:
        clause = "AND metric_id = %s"
        params.append(metric_id)
    rows = _db_fetch_all(
        f"""
        SELECT id, authority_id, metric_id, period, value, provenance
        FROM monitoring_timeseries
        WHERE authority_id = %s {clause}
        ORDER BY period DESC
        """,
        tuple(params),
    )
    items = [_row_to_timeseries(r) for r in rows]
    return JSONResponse(content=jsonable_encoder({"monitoring_timeseries": items}))


def _row_to_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "monitoring_event_id": str(row["id"]),
        "authority_id": row["authority_id"],
        "event_type": row["event_type"],
        "event_date": row["event_date"],
        "payload": row.get("payload_jsonb") or {},
        "provenance": row.get("provenance") or {},
    }


def _row_to_timeseries(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "timeseries_id": str(row["id"]),
        "authority_id": row["authority_id"],
        "metric_id": row["metric_id"],
        "period": row["period"],
        "value": row.get("value"),
        "provenance": row.get("provenance") or {},
    }
