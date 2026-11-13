import time

import pytest
from fastapi.testclient import TestClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

from incidentlab.api import create_app
from incidentlab.otlp import decode
from incidentlab.store import Store


def payload():
    request = ExportTraceServiceRequest()
    resource = request.resource_spans.add()
    attr = resource.resource.attributes.add(key="service.name")
    attr.value.string_value = "checkout"
    span = resource.scope_spans.add().spans.add()
    span.trace_id = bytes.fromhex("01" * 16)
    span.span_id = bytes.fromhex("02" * 8)
    span.name = "GET /request"
    span.kind = 2
    span.start_time_unix_nano = time.time_ns() - 20_000_000
    span.end_time_unix_nano = span.start_time_unix_nano + 10_000_000
    return request


@pytest.fixture
def client():
    store = Store(":memory:")
    app = create_app(store, run_lab=False)
    with TestClient(app) as client:
        yield client
    store.close()


def test_otlp_ingestion_flows_through_storage_to_api(client):
    response = client.post(
        "/v1/traces",
        content=payload().SerializeToString(),
        headers={"content-type": "application/x-protobuf"},
    )
    assert response.status_code == 200
    overview = client.get("/api/overview").json()
    assert overview["request_count"] == 1
    assert overview["services"][0]["service"] == "checkout"
    traces = client.get("/api/traces").json()
    detail = client.get(f"/api/traces/{traces[0]['trace_id']}").json()
    assert detail[0]["duration_ms"] == 10


def test_duplicate_ingestion_is_idempotent(client):
    body = payload().SerializeToString()
    for _ in range(2):
        assert (
            client.post(
                "/v1/traces", content=body, headers={"content-type": "application/x-protobuf"}
            ).status_code
            == 200
        )
    assert client.get("/api/overview").json()["span_count"] == 1


@pytest.mark.parametrize(
    ("body", "headers", "status"),
    [
        (b"invalid", {"content-type": "application/x-protobuf"}, 400),
        (b"{}", {"content-type": "application/json"}, 415),
        (b"a" * (2 * 1024 * 1024 + 1), {"content-type": "application/x-protobuf"}, 413),
        (b"", {"content-type": "application/x-protobuf", "content-encoding": "gzip"}, 415),
    ],
)
def test_rejects_bad_telemetry(client, body, headers, status):
    assert client.post("/v1/traces", content=body, headers=headers).status_code == status


def test_rejects_cross_origin_controls(client):
    assert (
        client.post(
            "/api/experiments", json={"scenario": "healthy"}, headers={"origin": "https://untrusted.example"}
        ).status_code
        == 403
    )


def test_scenario_validation_and_warmup_guard(client):
    assert client.post("/api/experiments", json={"scenario": "arbitrary"}).status_code == 422
    assert client.post("/api/experiments", json={"scenario": "healthy"}).status_code == 409


def test_trace_and_incident_validation(client):
    assert client.get("/api/traces/not-a-trace").status_code == 422
    assert client.get("/api/traces/" + "ab" * 16).status_code == 404
    assert client.get("/api/incidents/missing").status_code == 404


def test_empty_evaluation_does_not_invent_accuracy(client):
    report = client.get("/api/report").json()
    assert report["top1_accuracy"] is None
    assert report["control_false_positive_rate"] is None


def test_rejects_invalid_span_time():
    request = payload()
    request.resource_spans[0].scope_spans[0].spans[0].end_time_unix_nano = 1
    with pytest.raises(ValueError):
        decode(request.SerializeToString())


def test_rejects_zero_span_ids():
    request = payload()
    request.resource_spans[0].scope_spans[0].spans[0].trace_id = b"\x00" * 16
    with pytest.raises(ValueError):
        decode(request.SerializeToString())


def test_data_survives_store_restart(tmp_path):
    path = str(tmp_path / "traces.db")
    first = Store(path)
    first.insert(decode(payload().SerializeToString()))
    first.save_incident({"id": "run", "created_at": time.time(), "title": "Persistent run"})
    first.close()
    second = Store(path)
    assert len(second.trace("01" * 16)) == 1
    assert second.incidents()[0]["title"] == "Persistent run"
    second.close()
