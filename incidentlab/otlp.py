import math
import time

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from incidentlab.models import Span


def value(item):
    kind = item.WhichOneof("value")
    if kind == "array_value":
        return [value(v) for v in item.array_value.values]
    if kind == "kvlist_value":
        return {v.key: value(v.value) for v in item.kvlist_value.values}
    result = getattr(item, kind) if kind else None
    if isinstance(result, bytes):
        return result.hex()
    if isinstance(result, float) and not math.isfinite(result):
        return str(result)
    return result


def decode(body: bytes) -> list[Span]:
    request = ExportTraceServiceRequest()
    request.ParseFromString(body)
    spans = []
    now = time.time_ns()
    for resource in request.resource_spans:
        attributes = {a.key: value(a.value) for a in resource.resource.attributes}
        service = str(attributes.get("service.name", "unknown"))[:120]
        for scope in resource.scope_spans:
            for span in scope.spans:
                if len(spans) >= 5000:
                    raise ValueError("At most 5000 spans per request")
                if (
                    len(span.trace_id) != 16
                    or len(span.span_id) != 8
                    or not any(span.trace_id)
                    or not any(span.span_id)
                ):
                    raise ValueError("Invalid trace or span ID")
                if span.end_time_unix_nano < span.start_time_unix_nano:
                    raise ValueError("Span ends before it starts")
                if not now - 86400 * 10**9 <= span.start_time_unix_nano <= now + 60 * 10**9:
                    raise ValueError("Span timestamp outside accepted retention window")
                spans.append(
                    Span(
                        trace_id=span.trace_id.hex(),
                        span_id=span.span_id.hex(),
                        parent_id=span.parent_span_id.hex(),
                        service=service,
                        name=span.name[:240],
                        kind=span.kind,
                        start_ns=span.start_time_unix_nano,
                        end_ns=span.end_time_unix_nano,
                        error=span.status.code == 2,
                        attributes={a.key: value(a.value) for a in span.attributes},
                        events=[
                            {
                                "name": e.name,
                                "time_ns": e.time_unix_nano,
                                "attributes": {a.key: value(a.value) for a in e.attributes},
                            }
                            for e in span.events
                        ],
                    )
                )
    return spans
