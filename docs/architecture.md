# Architecture and design decisions

## Workload and boundaries

The collector/control plane serves a bundled React dashboard and JSON API. Three independent FastAPI processes provide the observed application. A controller issues real HTTP requests at bounded concurrency, requests fault changes using a generated shared token, and persists the experiment outcome.

| Process   | Port | Responsibility                                                |
| --------- | ---- | ------------------------------------------------------------- |
| API       | 8100 | UI, OTLP ingestion, storage, diagnosis, experiment controller |
| checkout  | 8101 | Entry point, sequential inventory and payment dependencies    |
| inventory | 8102 | SQLite query operation                                        |
| payments  | 8103 | Payment authorization demonstration                           |

All launcher listeners bind `127.0.0.1`. The API must run with one worker: background traffic, baseline, and experiment coordination are process-local. Multiple API workers are unsupported.

## Why these choices

- **Python/FastAPI:** asynchronous HTTP and straightforward experiments, with SQLite and testing available locally.
- **React/TypeScript:** typed API consumers, responsive investigation views, native modal dialogs, and independently buildable static assets.
- **SQLite WAL:** durable telemetry without an external database prerequisite. Locking is explicit; inserts are idempotent by `(trace_id, span_id)`. This is single-machine storage, not distributed write scalability.
- **Standard OTLP protobuf:** real OpenTelemetry SDK and HTTP exporter. The collector implements uncompressed trace export, not the full collector suite. Bodies are capped at 2 MiB and 5,000 spans; IDs and timestamp bounds are validated.
- **Explicit instrumentation:** the lab owns server/client/SQL span boundaries and W3C propagation. FastAPI native tracing is disabled to avoid duplicate spans when an SDK provider is installed.
- **No model in the critical path:** reproduce and inspect diagnosis without API keys or nondeterministic explanation steps.

## Diagnosis algorithm

`diagnose(current, baseline)` cannot access the scenario catalog, fault controller, or injected target label.

1. Group SERVER spans by service. Require at least five current and five baseline samples per evaluated service.
2. Compare current p95 with baseline p95. Latency must exceed both `2.5 × baseline p95` and `baseline p95 + 70 ms`. An error-rate increase of at least 15 percentage points also triggers a candidate.
3. Estimate local time by subtracting the **union** of direct child intervals. Summing overlapping child durations would double-count concurrent work. Clip intervals to the parent boundary.
4. Look for local failures: failed server spans without observed failing descendants. This reduces scores for services propagating downstream errors.
5. Look for slow INTERNAL database operations with a `db.system.name` attribute. Generic framework wrapper spans do not qualify as database evidence.
6. Rank candidates with bounded weighted evidence scores. Include measured facts, an exemplar trace, investigation steps, and caveats.

Weights and thresholds are inspectable heuristics, not parameters learned from a representative incident corpus. A healthy result requires adequate current/baseline samples for observed services. Entirely unobserved services remain an instrumentation blind spot.

The live overview uses a rolling 60-second window. An anomaly can remain visible briefly after recovery because the window includes incident traffic. Saved experiments use a clean observation window and fresh baseline.

## Experiment lifecycle

Background traffic and experiments share an async lock, preventing background requests from contaminating experiment boundaries.

1. Reset every service to healthy.
2. Send 24 baseline requests, then wait for SDK batch export.
3. Apply one selected fault, or none for a control.
4. Send 30 requests, with at most three concurrent requests.
5. Diagnose from spans only, then attach ground truth and evaluate the top result.
6. Persist the incident.
7. In `finally`, attempt to reset all services. Save recovery confirmation only after reset succeeds; surface recovery failure in lab status.

Network errors abort collection instead of manufacturing observations. HTTP 5xx responses are expected evidence. Each service captures the fault state once per request. The control token is generated per launcher session and never exported into traces.

Recovery is best effort if the API is forcibly killed. The supervisor stops all service processes; a full restart begins with healthy in-memory states. Independently deployed fault injection would require durable fault leases.

## Security and exclusions

This is a trusted local lab. Unexpected browser Origins are rejected for mutations; internal controls require the generated token. Neither replaces authentication or network isolation. OTLP ingestion is unauthenticated on the local listener. Runtime telemetry, logs, virtual environments, and local configuration are ignored by Git.

Automatic remediation, production root-cause guarantees, multi-tenancy, independent log/metric pipelines, Kubernetes operators, and LLM agents are excluded. Broader evaluation and telemetry coverage are the next milestones.
