# Test an independent application

IncidentLab now has a collector-only mode for independently instrumented applications. It does not require the built-in checkout/inventory/payments services or their control endpoints.

## Verified example: Django Oscar shop

The reference application is the [Django Oscar upstream sandbox](https://github.com/django-oscar/django-oscar), pinned to commit `a5ed3c9c17d4cf6ee18aa9795b493172416ab68b`. It is a separate Django e-commerce application with catalogue templates, product forms, baskets, stock records, search, and ORM/database operations. It is not a live merchant deployment. Test products are generated locally; no real customer, order, or payment data is used.

The adapter leaves upstream tracked source unchanged. Local-only settings, ASGI startup, telemetry instrumentation, and fixture generation live in `examples/oscar/`. Upstream remains under its BSD-3-Clause license; its checkout and assets are not vendored into IncidentLab.

### Setup on Windows

First run IncidentLab's normal `python scripts/setup.py` if you have not already. Then, from the repository root:

```powershell
.venv\Scripts\python.exe scripts/oscar_demo.py setup
.venv\Scripts\python.exe scripts/oscar_demo.py verify --rounds 2
.venv\Scripts\python.exe scripts/oscar_demo.py run
```

On macOS/Linux substitute `.venv/bin/python`. The setup command downloads the pinned upstream source, creates a separate environment in `data/oscar-venv`, installs pinned Python dependencies, builds upstream assets from its own npm lock, migrates a dedicated SQLite database, and seeds 12 products. This requires internet and disk space; the test itself is local. Run only one local stack at a time because both modes use collector port 8100.

- Shop: http://127.0.0.1:8200/en-gb/catalogue/
- IncidentLab: http://127.0.0.1:8100
- Stop both with Ctrl+C.

`verify` starts and stops both processes itself. `run` keeps the shop and collector running for manual use. The Oscar telemetry database is separate from the built-in demo (`data/oscar-telemetry.db`). Experiment results survive a restart.

### What the test does

1. Opens the actual catalogue and product page, obtains the real CSRF token, submits the upstream add-to-basket form, and checks the product appears in the basket.
2. Sends 18 healthy catalogue requests and captures their telemetry as a named baseline.
3. Acquires a real `BEGIN EXCLUSIVE` transaction on the shop's SQLite database from a separate connection. The independent shop process now encounters database lock timeouts.
4. Sends 18 more requests, observes HTTP 500 responses and recorded database exceptions, and submits that observation window for diagnosis without supplying the fault target.
5. Verifies that `oscar-shop` is ranked and database evidence appears in the supporting trace.
6. Releases the lock in `finally`, sends 18 recovery requests, and verifies successful responses and a healthy diagnosis against the original baseline.
7. Repeats for the requested number of rounds and writes `data/oscar-verification.json`.

Django may fail while initializing a database connection, before a SQL cursor span exists. IncidentLab therefore supports both database CLIENT/INTERNAL spans and recorded exceptions with recognized database exception types. The trace carries the actual `database is locked` exception. The engine is not told the fault label or expected answer.

This example establishes interoperability with this application and instrumentation combination. It does not establish general production root-cause accuracy. Oscar is one observed service here, with local database spans; this example does not exercise a distributed shop deployment.

## Use the external dashboard

Browse the shop to generate traffic. In IncidentLab:

1. Check `oscar-shop` appears in the service view and traces.
2. While the application is healthy, click **Capture healthy baseline**. This captures the last 30 seconds and requires at least five SERVER spans for each named service.
3. Drive additional requests, then click **Analyse since baseline**. It analyses requests after the saved baseline window.
4. Open an investigation and supporting trace to inspect timings, attributes, and exception events.

The application mode never injects demo faults. The automatic verifier controls only this specific local fixture database. External analyses have no supplied ground-truth label and are excluded from the built-in demo's accuracy/false-positive statistics.

## Connect another application

Start the collector independently:

```powershell
python scripts/dev.py --external --no-build
```

Configure the application's OpenTelemetry SDK with:

```text
OTEL_SERVICE_NAME=my-application
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:8100/v1/traces
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_COMPRESSION=none
```

These variables configure an installed SDK/exporter; setting them alone does not instrument an application. Install the framework and database instrumentations, initialize the exporter/provider, and propagate W3C trace context across HTTP boundaries. For Django ASGI, include the Django instrumentation's ASGI extra. Follow the [official Django instrumentation guide](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html).

A public website URL alone cannot provide internal traces. Connect an application whose runtime you control and instrument. Use a local or staging copy for controlled failure tests.

## External API

- `GET /api/baselines`: recent baseline metadata, excluding full stored span snapshots.
- `POST /api/baselines`: `{"name":"Healthy app","services":["my-application"],"start":<epoch-seconds>,"end":<epoch-seconds>}`.
- `POST /api/analyses`: `{"baseline_id":"<id>","title":"Observation","start":<epoch-seconds>,"end":<epoch-seconds>}`.

Windows must be completed, nonoverlapping, within the last 24 hours, and at most one hour long. Baselines retain up to ten snapshots. Missing expected-service samples prevent a healthy verdict. Baseline snapshots survive collector restarts; supporting traces still follow ordinary retention limits. A snapshot does not certify that the application was healthy when it was captured.
