# Verification

## Unit and API checks

The suite covers fault ranking above cascading symptoms; healthy controls; insufficient baseline and low-sample abstention; overlapping child interval union; trace-scoped parent IDs; cyclic parent safety; OTLP ingestion through SQLite to the API; duplicate ingestion; malformed payloads; invalid IDs/times; body limits; unsupported compression/media types; cross-origin rejection; scenario/warm-up guards; missing resources; empty evaluation results; and persistence across restart.

## Real-service integration

`scripts/verify.py --start --rounds 2` starts the real API and three service processes with a temporary database. It repeats all five scenarios and checks:

1. The bundled dashboard is served and warm-up creates a baseline.
2. A concurrent experiment is rejected.
3. Faults rank the expected service first; a healthy control raises no incident.
4. At least 25 of the 30 expected observation traces arrive.
5. An exemplar trace spans at least two services with parent propagation.
6. The service dependency graph contains observed edges.
7. Recovery is recorded and all services respond successfully afterward.

The verifier exits nonzero on failure and writes `data/verification.json`. This small catalog is not a production accuracy benchmark.

## Browser checks

Inspect the overview, run an experiment, open supporting traces, search and filter, export results, and check narrow-screen layout. Also inspect loading and API failure states. These checks complement the service integration suite.

## Validation boundaries

The development environment runs Windows. GitHub Actions repeats the automated suite on Ubuntu, Python 3.12, and Node 24. A configured workflow is not evidence of a successful remote run; inspect the actual pushed commit's Actions result.

The separate Oscar adapter verifies interoperability with a pinned Django Oscar sandbox, including its real catalogue/basket flow and database-lock failures. See [external application verification](external-applications.md). No load-capacity, cross-machine clock-skew, production-security, or compatibility beyond the tested configuration is claimed. Measured results should always include workload, sample size, and environment.
