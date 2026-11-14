import time
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from incidentlab.api import create_app
from incidentlab.diagnosis import diagnose
from incidentlab.models import Span
from incidentlab.store import Store


def samples(service, start, failed=False, count=8):
    spans = []
    for index in range(count):
        begin = int((start + index * 0.05) * 1e9)
        duration = 250_000_000 if failed else 10_000_000
        spans.append(
            Span(
                trace_id=sha256(f"{service}:{start}:{index}".encode()).hexdigest()[:32],
                span_id=f"{index + 1:016x}",
                service=service,
                name="GET /catalogue/",
                kind=2,
                start_ns=begin,
                end_ns=begin + duration,
                error=failed,
            )
        )
        spans.append(
            Span(
                trace_id=spans[-1].trace_id,
                span_id=f"{index + 101:016x}",
                parent_id=spans[-1].span_id,
                service=service,
                name="SELECT",
                kind=3,
                start_ns=begin,
                end_ns=begin + duration,
                error=failed,
                attributes={"db.system": "sqlite"},
            )
        )
    return spans


@pytest.fixture
def external_client(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "external")
    store = Store(":memory:")
    app = create_app(store)
    with TestClient(app) as client:
        yield client, store
    store.close()


def create_baseline(client, start, services=None):
    return client.post(
        "/api/baselines",
        json={
            "name": "Healthy shop",
            "start": start,
            "end": start + 1,
            "services": services or ["independent-shop"],
        },
    )


def test_external_mode_does_not_start_demo_traffic(external_client):
    client, _ = external_client
    assert client.get("/api/health").json()["mode"] == "external"
    assert client.get("/api/scenarios").json() == []
    assert client.post("/api/experiments", json={"scenario": "healthy"}).status_code == 409
    assert client.get("/api/overview").json()["lab"]["phase"] == "external"


def test_independent_service_baseline_fault_recovery_and_report(external_client):
    client, store = external_client
    start = time.time() - 30
    store.insert(samples("independent-shop", start))
    response = create_baseline(client, start)
    assert response.status_code == 201
    baseline = response.json()
    assert "spans" not in baseline
    store.insert(samples("independent-shop", start + 5, failed=True))
    response = client.post(
        "/api/analyses", json={"baseline_id": baseline["id"], "start": start + 5, "end": start + 7}
    )
    assert response.status_code == 201
    incident = response.json()
    assert incident["diagnosis"]["suspects"][0]["service"] == "independent-shop"
    assert any("failed database" in e for e in incident["diagnosis"]["suspects"][0]["evidence"])
    assert incident["ground_truth"] is None and incident["top1_correct"] is None
    report = client.get("/api/report").json()
    assert report["external_analyses"] == 1 and report["control_runs"] == 0
    assert report["top1_accuracy"] is None and report["control_false_positive_rate"] is None
    store.insert(samples("independent-shop", start + 10))
    response = client.post(
        "/api/analyses", json={"baseline_id": baseline["id"], "start": start + 10, "end": start + 12}
    )
    assert response.json()["diagnosis"]["status"] == "healthy"


def test_rejects_overlapping_windows_missing_baselines_and_invalid_dates(external_client):
    client, store = external_client
    start = time.time() - 30
    store.insert(samples("independent-shop", start))
    baseline = create_baseline(client, start).json()
    assert (
        client.post(
            "/api/analyses", json={"baseline_id": baseline["id"], "start": start, "end": start + 5}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/analyses", json={"baseline_id": "missing", "start": start + 2, "end": start + 5}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/baselines", json={"name": "invalid", "start": start + 5, "end": start, "services": ["shop"]}
        ).status_code
        == 422
    )


def test_missing_expected_service_cannot_produce_healthy_result(external_client):
    client, store = external_client
    start = time.time() - 30
    store.insert(samples("independent-shop", start) + samples("warehouse", start))
    baseline = create_baseline(client, start, ["independent-shop", "warehouse"]).json()
    store.insert(samples("independent-shop", start + 5))
    response = client.post(
        "/api/analyses", json={"baseline_id": baseline["id"], "start": start + 5, "end": start + 7}
    )
    assert response.json()["diagnosis"]["status"] == "insufficient_data"


def test_baseline_requires_samples_from_every_named_service(external_client):
    client, store = external_client
    start = time.time() - 30
    store.insert(samples("independent-shop", start))
    assert create_baseline(client, start, ["independent-shop", "missing"]).status_code == 422


def test_baseline_snapshot_survives_collector_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_MODE", "external")
    path = str(tmp_path / "external.db")
    first = Store(path)
    start = time.time() - 20
    first.insert(samples("independent-shop", start))
    with TestClient(create_app(first)) as client:
        assert create_baseline(client, start).status_code == 201
    first.close()
    second = Store(path)
    app = create_app(second)
    with TestClient(app) as client:
        assert client.get("/api/baselines").json()[0]["services"] == ["independent-shop"]
        assert len(app.state.lab.baseline) == 16
    second.close()


def test_client_database_span_is_supported_without_framework_specific_names():
    start = time.time() - 30
    result = diagnose(samples("shop", start + 5, failed=True), samples("shop", start))
    suspect = result["suspects"][0]
    assert suspect["service"] == "shop"
    assert any("failed database operations" in e for e in suspect["evidence"])


def test_database_connection_failure_is_explained_without_a_sql_child_span():
    start = time.time() - 30
    current = [s for s in samples("shop", start + 5, failed=True) if s.kind == 2]
    for row in current:
        row.events = [
            {
                "name": "exception",
                "attributes": {
                    "exception.type": "django.db.utils.OperationalError",
                    "exception.message": "database is locked",
                },
            }
        ]
    result = diagnose(current, samples("shop", start))
    assert result["status"] == "incident"
    assert any("database is locked" in e for e in result["suspects"][0]["evidence"])
    assert "database" in result["suspects"][0]["recommendation"].lower()
