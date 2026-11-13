import pytest

from incidentlab.diagnosis import diagnose, exclusive_ms, percentile, topology
from incidentlab.models import Span


def span(service, span_id, parent="", duration=10, error=False, trace_id="t", kind=2, start=0):
    return Span(
        service=service,
        span_id=span_id,
        parent_id=parent,
        duration=duration,
        error=error,
        trace_id=trace_id,
        kind=kind,
        name="operation",
        attributes={"db.system.name": "sqlite"} if kind == 1 else {},
        start_ns=int(start * 1e6),
        end_ns=int((start + duration) * 1e6),
    )


def traffic(target=None, mode="latency", count=12):
    spans = []
    for i in range(count):
        trace = f"trace{i}"
        inventory_ms = 360 if target == "inventory" and mode == "latency" else 15
        payment_ms = 15
        local_ms = 350 if target == "checkout" else 10
        inventory_error = target == "inventory" and mode == "errors"
        payment_error = target == "payments" and mode == "errors"
        spans.extend(
            [
                span(
                    "checkout",
                    "root",
                    duration=inventory_ms + payment_ms + local_ms,
                    error=inventory_error or payment_error,
                    trace_id=trace,
                ),
                span(
                    "checkout",
                    "client-i",
                    "root",
                    duration=inventory_ms,
                    error=inventory_error,
                    trace_id=trace,
                    kind=3,
                    start=5,
                ),
                span(
                    "inventory",
                    "server-i",
                    "client-i",
                    duration=inventory_ms,
                    error=inventory_error,
                    trace_id=trace,
                    start=5,
                ),
            ]
        )
        if not inventory_error:
            spans.append(
                span(
                    "inventory", "db", "server-i", duration=inventory_ms - 2, trace_id=trace, kind=1, start=6
                )
            )
        if not inventory_error:
            spans.extend(
                [
                    span(
                        "checkout",
                        "client-p",
                        "root",
                        duration=payment_ms,
                        error=payment_error,
                        trace_id=trace,
                        kind=3,
                        start=5 + inventory_ms,
                    ),
                    span(
                        "payments",
                        "server-p",
                        "client-p",
                        duration=payment_ms,
                        error=payment_error,
                        trace_id=trace,
                        start=5 + inventory_ms,
                    ),
                ]
            )
    return spans


@pytest.mark.parametrize(
    ("target", "mode"),
    [("inventory", "latency"), ("inventory", "errors"), ("payments", "errors"), ("checkout", "latency")],
)
def test_local_fault_ranks_above_cascading_symptoms(target, mode):
    result = diagnose(traffic(target, mode), traffic())
    assert result["status"] == "incident"
    assert result["suspects"][0]["service"] == target


def test_healthy_traffic_does_not_trigger_incident():
    assert diagnose(traffic(), traffic())["status"] == "healthy"


def test_insufficient_baseline_abstains():
    result = diagnose(traffic("inventory"), [])
    assert result["status"] == "insufficient_data"
    assert not result["suspects"]


def test_low_sample_count_abstains():
    assert diagnose(traffic("inventory", count=2), traffic())["status"] == "insufficient_data"


def test_exclusive_time_subtracts_union_not_sum():
    parent = span("checkout", "root", duration=100)
    children = [span("checkout", "a", duration=60, start=10), span("checkout", "b", duration=60, start=30)]
    assert exclusive_ms(parent, children) == 20


def test_exclusive_time_clips_outside_parent():
    parent = span("checkout", "root", duration=100)
    assert exclusive_ms(parent, [span("checkout", "a", duration=150, start=-20)]) == 0


def test_parent_ids_are_scoped_by_trace():
    spans = [span("checkout", "same", trace_id="first"), span("payments", "child", "same", trace_id="second")]
    assert topology(spans) == []


def test_topology_discovers_cross_service_edges():
    edges = topology(traffic())
    assert {(e["source"], e["target"]) for e in edges} == {
        ("checkout", "inventory"),
        ("checkout", "payments"),
    }
    assert all(e["calls"] == 12 for e in edges)


def test_percentiles_interpolate_and_handle_empty_input():
    assert percentile([], 0.95) == 0
    assert percentile([10], 0.95) == 10
    assert percentile([0, 100], 0.95) == 95


def test_missing_child_does_not_crash_ranking():
    current = [s for s in traffic("payments", "errors") if s.kind != 3]
    result = diagnose(current, traffic())
    assert result["status"] == "incident"
    assert result["caveats"]


def test_cyclic_parent_graph_is_bounded():
    rows = traffic("payments", "errors")
    rows.extend(
        [
            span("payments", "cycle-a", "cycle-b", error=True),
            span("payments", "cycle-b", "cycle-a", error=True),
        ]
    )
    assert diagnose(rows, traffic())["status"] == "incident"
