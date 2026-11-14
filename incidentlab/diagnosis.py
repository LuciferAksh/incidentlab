"""Deterministic ranking from traces only; no scenario labels or control-plane inputs."""

import math
from collections import defaultdict
from statistics import median

from incidentlab.models import Span


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def exclusive_ms(span: Span, children: list[Span]) -> float:
    """Subtract the UNION of child intervals, including overlapping async children."""
    intervals = sorted(
        (max(span.start_ns, s.start_ns), min(span.end_ns, s.end_ns))
        for s in children
        if min(span.end_ns, s.end_ns) > max(span.start_ns, s.start_ns)
    )
    covered = 0
    end = span.start_ns
    for start, stop in intervals:
        covered += max(0, stop - max(start, end))
        end = max(end, stop)
    return max(0.0, span.duration_ms - covered / 1e6)


def groups(spans: list[Span]) -> dict[str, list[Span]]:
    grouped = defaultdict(list)
    for span in spans:
        # SERVER spans are the service-level unit. Database spans belong to their service.
        if span.kind == 2:
            grouped[span.service].append(span)
    return dict(grouped)


def summarize(spans: list[Span]) -> list[dict]:
    return [
        {
            "service": service,
            "requests": len(rows),
            "error_rate": sum(s.error for s in rows) / len(rows),
            "p50_ms": round(percentile([s.duration_ms for s in rows], 0.5), 2),
            "p95_ms": round(percentile([s.duration_ms for s in rows], 0.95), 2),
        }
        for service, rows in sorted(groups(spans).items())
    ]


def diagnose(current: list[Span], baseline: list[Span], min_samples: int = 5) -> dict:
    current_groups, baseline_groups = groups(current), groups(baseline)
    by_parent = defaultdict(list)
    by_key = {(s.trace_id, s.span_id): s for s in current}
    baseline_children = defaultdict(list)
    for s in current:
        by_parent[(s.trace_id, s.parent_id)].append(s)
    for s in baseline:
        baseline_children[(s.trace_id, s.parent_id)].append(s)
    suspects = []
    for service, rows in current_groups.items():
        normal = baseline_groups.get(service, [])
        if len(rows) < min_samples or len(normal) < min_samples:
            continue
        base_ms = median(s.duration_ms for s in normal)
        p95 = percentile([s.duration_ms for s in rows], 0.95)
        normal_p95 = percentile([s.duration_ms for s in normal], 0.95)
        error_rate = sum(s.error for s in rows) / len(rows)
        base_error = sum(s.error for s in normal) / len(normal)
        error_delta = max(0, error_rate - base_error)
        # Both an absolute and relative floor protect near-zero baselines.
        latency_anomaly = p95 > max(normal_p95 * 2.5, normal_p95 + 70)
        error_anomaly = error_delta >= 0.15
        if not latency_anomaly and not error_anomaly:
            continue
        self_ms = median(exclusive_ms(s, by_parent[(s.trace_id, s.span_id)]) for s in rows)
        base_self = median(exclusive_ms(s, baseline_children[(s.trace_id, s.span_id)]) for s in normal)
        self_increase = max(0, self_ms - base_self)
        local_errors = 0
        for row in rows:
            # A failing descendant means this service may only be propagating the error.
            stack = list(by_parent[(row.trace_id, row.span_id)])
            descendant_failed = False
            visited = set()
            while stack:
                child = stack.pop()
                key = (child.trace_id, child.span_id)
                if key in visited:
                    continue
                visited.add(key)
                descendant_failed |= child.error
                stack.extend(by_parent[key])
            local_errors += bool(row.error and not descendant_failed)
        local_error_rate = local_errors / len(rows)
        score = min(100.0, 10 + 50 * min(1, self_increase / 300) + 70 * local_error_rate + 10 * error_delta)
        # Standard database instrumentations use CLIENT spans and may emit legacy db.system.
        # A database failure is local dependency evidence, rather than a remote service symptom.
        internal = [
            s
            for s in current
            if s.service == service
            and s.kind in {1, 3}
            and ("db.system.name" in s.attributes or "db.system" in s.attributes)
        ]
        slow_internal = [s for s in internal if s.duration_ms > max(base_ms * 3, 100)]
        failed_database = [s for s in internal if s.error]
        database_exceptions = [
            event["attributes"]
            for row in rows
            if row.error
            for event in row.events
            if str(event.get("attributes", {}).get("exception.type", "")).startswith(
                ("sqlite3.", "django.db.", "psycopg", "sqlalchemy.exc.", "pymysql.", "asyncpg.")
            )
        ]
        if slow_internal or failed_database or database_exceptions:
            score = min(100.0, score + 55)
        evidence = [
            f"p95 {p95:.1f} ms versus baseline {normal_p95:.1f} ms",
            f"errors {error_rate:.0%} versus baseline {base_error:.0%}",
            f"exclusive time increase {self_increase:.1f} ms",
        ]
        if local_errors:
            evidence.append(f"{local_errors} failures without a failed child span")
        if slow_internal:
            evidence.append(f"{len(slow_internal)} slow internal operations: {slow_internal[0].name}")
        if failed_database:
            evidence.append(f"{len(failed_database)} failed database operations: {failed_database[0].name}")
        if database_exceptions:
            exception = database_exceptions[0]
            evidence.append(
                f"Database exception {exception['exception.type']}: {str(exception.get('exception.message', ''))[:240]}"
            )
        exemplar = max(rows, key=lambda s: (s.error, s.duration_ms))
        suspects.append(
            {
                "service": service,
                "score": round(score, 1),
                "evidence": evidence,
                "trace_id": exemplar.trace_id,
                "p95_ms": round(p95, 1),
                "baseline_p95_ms": round(normal_p95, 1),
                "error_rate": error_rate,
                "local_error_rate": local_error_rate,
                "recommendation": (
                    "Inspect the database operation, query latency, and exception events in the linked trace."
                    if slow_internal or failed_database or database_exceptions
                    else "Inspect the local exception events and recent service changes."
                    if local_errors
                    else "Inspect downstream dependencies before changing this service."
                ),
            }
        )
    suspects.sort(key=lambda item: (-item["score"], item["service"]))
    observed = set(current_groups)
    missing = sorted(observed - set(baseline_groups))
    return {
        "status": "incident"
        if suspects
        else "healthy"
        if observed
        and all(
            len(current_groups[s]) >= min_samples and len(baseline_groups.get(s, [])) >= min_samples
            for s in observed
        )
        else "insufficient_data",
        "suspects": suspects,
        "method": "Trace-derived latency/error changes + exclusive time + local failure evidence",
        "caveats": [
            "Ranking scores are heuristic evidence scores, not probabilities or proof of causation.",
            "Incomplete traces, missing services, and concurrent faults can change the ranking.",
        ]
        + ([f"No baseline for: {', '.join(missing)}"] if missing else []),
        "sample_count": len(by_key),
    }


def topology(spans: list[Span]) -> list[dict]:
    index = {(s.trace_id, s.span_id): s for s in spans}
    edges = defaultdict(lambda: {"calls": 0, "errors": 0, "durations": []})
    for span in spans:
        parent = index.get((span.trace_id, span.parent_id))
        if parent and parent.service != span.service:
            edge = edges[(parent.service, span.service)]
            edge["calls"] += 1
            edge["errors"] += int(span.error)
            edge["durations"].append(span.duration_ms)
    return [
        {
            "source": src,
            "target": dst,
            "calls": data["calls"],
            "errors": data["errors"],
            "p95_ms": round(percentile(data["durations"], 0.95), 1),
        }
        for (src, dst), data in sorted(edges.items())
    ]
