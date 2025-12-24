from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator

_initialized = False
_enabled = False
_tracer = None


def _setup_tracer() -> None:
    global _initialized, _enabled, _tracer
    if _initialized:
        return
    _initialized = True

    endpoint = os.environ.get("PHOENIX_OTLP_ENDPOINT")
    host = os.environ.get("PHOENIX_HOST")
    port = os.environ.get("PHOENIX_PORT") or "6006"
    if not endpoint and host:
        endpoint = f"http://{host}:{port}/v1/traces"
    if not endpoint:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        return

    service_name = os.environ.get("PHOENIX_SERVICE_NAME", "tpa-api")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)
    _enabled = True


def _get_tracer():
    _setup_tracer()
    if _enabled:
        return _tracer
    return None


@contextmanager
def trace_span(name: str, attributes: Dict[str, Any] | None = None) -> Iterator[Any]:
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                if value is None:
                    continue
                span.set_attribute(key, value)
        yield span
