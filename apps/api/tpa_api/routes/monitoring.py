from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.monitoring import MonitoringEventCreate, MonitoringTimeseriesCreate
from ..services.monitoring import create_monitoring_event as service_create_monitoring_event
from ..services.monitoring import create_monitoring_timeseries as service_create_monitoring_timeseries
from ..services.monitoring import list_monitoring_events as service_list_monitoring_events
from ..services.monitoring import list_monitoring_timeseries as service_list_monitoring_timeseries


router = APIRouter(tags=["monitoring"])


@router.post("/monitoring/events")
def create_monitoring_event(body: MonitoringEventCreate) -> JSONResponse:
    return service_create_monitoring_event(body)


@router.get("/monitoring/events")
def list_monitoring_events(authority_id: str) -> JSONResponse:
    return service_list_monitoring_events(authority_id)


@router.post("/monitoring/timeseries")
def create_monitoring_timeseries(body: MonitoringTimeseriesCreate) -> JSONResponse:
    return service_create_monitoring_timeseries(body)


@router.get("/monitoring/timeseries")
def list_monitoring_timeseries(authority_id: str, metric_id: str | None = None) -> JSONResponse:
    return service_list_monitoring_timeseries(authority_id, metric_id=metric_id)
