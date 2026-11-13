import os

import httpx
from fastapi import Request
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode


def setup(service: str) -> TracerProvider:
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://127.0.0.1:8100/v1/traces"),
                timeout=5,
            ),
            schedule_delay_millis=100,
        )
    )
    trace.set_tracer_provider(provider)
    return provider


def install_middleware(app, tracer):
    @app.middleware("http")
    async def server_span(request: Request, call_next):
        if request.url.path in {"/health", "/control"}:
            return await call_next(request)
        with tracer.start_as_current_span(
            f"{request.method} {request.url.path}",
            context=propagate.extract(dict(request.headers)),
            kind=SpanKind.SERVER,
            attributes={"http.request.method": request.method, "url.path": request.url.path},
        ) as span:
            try:
                response = await call_next(request)
                span.set_attribute("http.response.status_code", response.status_code)
                if response.status_code >= 500:
                    span.set_status(Status(StatusCode.ERROR))
                return response
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR))
                raise


async def call(client: httpx.AsyncClient, tracer, target: str, url: str) -> httpx.Response:
    with tracer.start_as_current_span(
        f"GET {target}", kind=SpanKind.CLIENT, attributes={"server.address": target}
    ) as span:
        headers = {}
        propagate.inject(headers)
        response = await client.get(url, headers=headers)
        span.set_attribute("http.response.status_code", response.status_code)
        if response.is_error:
            span.set_status(Status(StatusCode.ERROR))
        return response
