"""Exercise the actual collector, HTTP services, diagnosis, traces, and recovery."""

import argparse
import contextlib
import json
import sys
import tempfile
import time
from pathlib import Path

import httpx
from dev import ROOT, RunningLab, interpreter


def wait(client, predicate, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = client.get("/api/overview")
        result.raise_for_status()
        overview = result.json()
        if overview["lab"]["phase"] == "error":
            raise RuntimeError(overview["lab"]["message"])
        if predicate(overview):
            return overview
        time.sleep(0.3)
    raise TimeoutError("Lab did not reach the expected state")


def verify(base_url: str, rounds: int) -> dict:
    results = []
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        wait(client, lambda overview: overview["lab"]["phase"] == "idle")
        response = client.get("/")
        assert response.status_code == 200 and "IncidentLab" in response.text, "Dashboard not served"
        scenarios = client.get("/api/scenarios").json()
        for _round in range(rounds):
            for scenario in scenarios:
                response = client.post("/api/experiments", json={"scenario": scenario["id"]})
                assert response.status_code == 202, response.text
                run_id = response.json()["run_id"]
                duplicate = client.post("/api/experiments", json={"scenario": "healthy"})
                assert duplicate.status_code == 409, "Concurrent experiments were not rejected"
                overview = wait(
                    client,
                    lambda o, expected=run_id: (
                        o["lab"]["phase"] == "idle" and any(i["id"] == expected for i in o["incidents"])
                    ),
                )
                incident = client.get(f"/api/incidents/{run_id}").json()
                assert incident["top1_correct"], f"Incorrect ranking: {json.dumps(incident)}"
                assert incident["trace_count"] >= 25, "Telemetry was incomplete"
                if scenario["service"]:
                    suspect = incident["diagnosis"]["suspects"][0]
                    trace = client.get(f"/api/traces/{suspect['trace_id']}")
                    assert trace.status_code == 200
                    spans = trace.json()
                    assert len(spans) >= 3, "No distributed trace found"
                    assert len({s["service"] for s in spans}) >= 2
                    assert any(s["parent_id"] for s in spans), "Parent context was not propagated"
                    assert overview["topology"], "No service graph was derived"
                assert incident["timeline"][-1]["message"] == "Fault removed; services restored"
                results.append(
                    {
                        "scenario": scenario["id"],
                        "run_id": run_id,
                        "top1_correct": incident["top1_correct"],
                        "trace_count": incident["trace_count"],
                        "duration_seconds": incident["duration_seconds"],
                    }
                )
                print(
                    f"PASS {scenario['id']}: {incident['trace_count']} traces, {incident['duration_seconds']}s",
                    flush=True,
                )
        # Check that restored services really respond, independently of the controller status.
        for port in [8101, 8102, 8103]:
            with httpx.Client(trust_env=False) as services:
                assert services.get(f"http://127.0.0.1:{port}/request", timeout=5).status_code == 200
        report = {
            "verified_at": time.time(),
            "rounds": rounds,
            "results": results,
            "scope": "Real local HTTP services; deterministic injected faults. Not a production benchmark.",
        }
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", action="store_true", help="Start and stop an isolated local lab")
    parser.add_argument("--base-url", default="http://127.0.0.1:8100")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--output", default="data/verification.json")
    args = parser.parse_args()
    if not 1 <= args.rounds <= 20:
        parser.error("--rounds must be between 1 and 20")
    with tempfile.TemporaryDirectory(prefix="incidentlab-verify-") as directory:
        manager = (
            RunningLab(interpreter(), db_path=str(Path(directory) / "test.db"))
            if args.start
            else contextlib.nullcontext()
        )
        with manager:
            report = verify(args.base_url, args.rounds)
    path = Path(args.output)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nVerified {len(report['results'])} experiments. Report: {path}")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, RuntimeError, TimeoutError, httpx.HTTPError) as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
