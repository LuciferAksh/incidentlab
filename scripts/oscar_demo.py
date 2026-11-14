"""Set up, run, and verify a separate upstream e-commerce app against IncidentLab."""

import argparse
import contextlib
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
import venv
from concurrent.futures import ThreadPoolExecutor

import httpx
from dev import ROOT, RunningLab, check_port, interpreter

UPSTREAM = ROOT / "data/external/django-oscar"
VENV = ROOT / "data/oscar-venv"
ADAPTER = ROOT / "examples/oscar/app.py"
SHOP_DB = ROOT / "data/oscar-shop.sqlite3"


def shop_python():
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def setup():
    metadata = json.loads((ROOT / "examples/oscar/upstream.json").read_text(encoding="utf-8"))
    UPSTREAM.parent.mkdir(parents=True, exist_ok=True)
    if not UPSTREAM.exists():
        subprocess.run(
            ["git", "clone", "--no-checkout", "--filter=blob:none", metadata["repository"], str(UPSTREAM)],
            check=True,
        )
        subprocess.run(["git", "-C", str(UPSTREAM), "checkout", "--detach", metadata["commit"]], check=True)
    current = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
    if current != metadata["commit"]:
        raise RuntimeError(
            "The external checkout differs from the pinned revision. Use a separate checkout; no source was overwritten."
        )
    if not shop_python().exists():
        venv.EnvBuilder(with_pip=True).create(VENV)
    subprocess.run(
        [str(shop_python()), "-m", "pip", "install", "-r", str(ROOT / "examples/oscar/requirements.lock")],
        check=True,
    )
    subprocess.run([str(shop_python()), "-m", "pip", "install", "--no-deps", "-e", str(UPSTREAM)], check=True)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run([npm, "ci", "--ignore-scripts", "--no-audit"], cwd=UPSTREAM, check=True)
    subprocess.run([npm, "run", "build"], cwd=UPSTREAM, check=True)
    subprocess.run([str(shop_python()), str(ADAPTER), "setup"], cwd=ROOT, check=True)


@contextlib.contextmanager
def shop():
    if not shop_python().exists() or not SHOP_DB.exists():
        raise RuntimeError("Run python scripts/oscar_demo.py setup first")
    check_port(8200)
    with (ROOT / "data/oscar-shop.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [str(shop_python()), str(ADAPTER), "serve"], cwd=ROOT, stdout=log, stderr=log
        )
        try:
            deadline = time.monotonic() + 30
            with httpx.Client(trust_env=False, timeout=3, follow_redirects=True) as client:
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("Oscar exited; inspect data/oscar-shop.log")
                    try:
                        response = client.get("http://127.0.0.1:8200/en-gb/catalogue/")
                        if response.status_code == 200 and "Engineering Notebook" in response.text:
                            break
                    except httpx.RequestError:
                        pass
                    time.sleep(0.2)
                else:
                    raise RuntimeError("Shop did not become ready; inspect data/oscar-shop.log")
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


def send_traffic(count: int = 18) -> dict:
    start = time.time()
    with httpx.Client(base_url="http://127.0.0.1:8200", timeout=5, trust_env=False) as client:

        def request(_):
            response = client.get("/en-gb/catalogue/")
            return response.status_code

        with ThreadPoolExecutor(max_workers=3) as pool:
            statuses = list(pool.map(request, range(count)))
    time.sleep(0.7)  # Real SDK export is asynchronous.
    return {
        "start": start,
        "end": time.time(),
        "requests": count,
        "successful": sum(status == 200 for status in statuses),
        "failed": sum(status >= 500 for status in statuses),
    }


def verify_cart() -> dict:
    # Follow the actual CSRF-protected product form; no fixture shortcut for basket writes.
    with httpx.Client(
        base_url="http://127.0.0.1:8200", timeout=5, trust_env=False, follow_redirects=True
    ) as client:
        catalogue = client.get("/en-gb/catalogue/")
        product_path = re.search(r'href="([^"]*/catalogue/engineering-notebook-[^"]*)"', catalogue.text)
        if product_path is None:
            raise RuntimeError("Could not find a seeded product in Oscar's catalogue")
        detail = client.get(product_path.group(1))
        action = re.search(r'action="([^"]*/basket/add/\d+/)"', detail.text)
        csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', detail.text)
        if action is None or csrf is None:
            raise RuntimeError("Oscar product page did not provide an add-to-basket form")
        added = client.post(
            action.group(1),
            data={"csrfmiddlewaretoken": csrf.group(1), "quantity": "1"},
            headers={"Referer": str(detail.url)},
        )
        basket = client.get("/en-gb/basket/")
        if added.status_code != 200 or basket.status_code != 200 or "Engineering Notebook" not in basket.text:
            raise RuntimeError("The real basket flow failed")
        return {
            "catalogue_status": catalogue.status_code,
            "product_status": detail.status_code,
            "basket_status": basket.status_code,
            "product_in_basket": True,
        }


def verify(rounds: int) -> dict:
    outcomes = []
    with httpx.Client(base_url="http://127.0.0.1:8100", timeout=10, trust_env=False) as collector:
        cart = verify_cart()
        for repeat in range(rounds):
            normal = send_traffic()
            assert normal["successful"] == normal["requests"], normal
            response = collector.post(
                "/api/baselines",
                json={
                    **{k: normal[k] for k in ["start", "end"]},
                    "name": f"Oscar healthy catalogue {repeat + 1}",
                    "services": ["oscar-shop"],
                },
            )
            response.raise_for_status()
            baseline = response.json()
            # A real SQLite EXCLUSIVE transaction blocks the independent application's
            # database reads. No app handler, OTel span, or response is mocked.
            with sqlite3.connect(SHOP_DB, timeout=1) as lock:
                lock.execute("BEGIN EXCLUSIVE")
                try:
                    failed = send_traffic()
                finally:
                    lock.rollback()
            assert failed["failed"] == failed["requests"], failed
            fault_response = collector.post(
                "/api/analyses",
                json={
                    "baseline_id": baseline["id"],
                    "start": failed["start"],
                    "end": failed["end"],
                    "title": "Oscar catalogue: database locked",
                },
            )
            fault_response.raise_for_status()
            fault = fault_response.json()
            assert fault["diagnosis"]["status"] == "incident", fault
            assert fault["diagnosis"]["suspects"][0]["service"] == "oscar-shop", fault
            assert any("database" in e.lower() for e in fault["diagnosis"]["suspects"][0]["evidence"]), fault
            trace = collector.get("/api/traces/" + fault["diagnosis"]["suspects"][0]["trace_id"])
            trace.raise_for_status()
            assert any(
                s["error"] and ("db.system" in s["attributes"] or "db.system.name" in s["attributes"])
                for s in trace.json()
            ) or any(
                "database is locked" in str(event.get("attributes", {}).get("exception.message", "")).lower()
                for span in trace.json()
                for event in span["events"]
            ), "Missing real database error evidence"
            healthy = send_traffic()
            assert healthy["successful"] == healthy["requests"], healthy
            control_response = collector.post(
                "/api/analyses",
                json={
                    "baseline_id": baseline["id"],
                    "start": healthy["start"],
                    "end": healthy["end"],
                    "title": "Oscar catalogue: recovered control",
                },
            )
            control_response.raise_for_status()
            control = control_response.json()
            assert control["diagnosis"]["status"] == "healthy", control
            outcomes.append(
                {
                    "round": repeat + 1,
                    "baseline": baseline,
                    "fault": failed,
                    "recovered": healthy,
                    "fault_incident_id": fault["id"],
                    "recovery_incident_id": control["id"],
                    "top_suspect": fault["diagnosis"]["suspects"][0]["service"],
                    "evidence": fault["diagnosis"]["suspects"][0]["evidence"],
                    "recovery_status": control["diagnosis"]["status"],
                }
            )
            print(
                f"PASS round {repeat + 1}: {failed['failed']} database-lock failures diagnosed; {healthy['successful']} recovered requests healthy",
                flush=True,
            )
        metadata = json.loads((ROOT / "examples/oscar/upstream.json").read_text(encoding="utf-8"))
        return {
            "verified_at": time.time(),
            "upstream": metadata,
            "cart": cart,
            "results": outcomes,
            "scope": "Local upstream Oscar sandbox, fixture products, real ORM/SQLite operations; controlled database lock. Not a production deployment or general accuracy benchmark.",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "run", "verify"])
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()
    if args.command == "setup":
        setup()
        return
    if not 1 <= args.rounds <= 10:
        parser.error("rounds must be between 1 and 10")
    if not (ROOT / "web/dist/index.html").exists():
        raise RuntimeError("Build the dashboard first: npm run build")
    if os.name != "nt":
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    with (
        RunningLab(interpreter(), str(ROOT / "data/oscar-telemetry.db"), external=True) as lab,
        shop() as process,
    ):
        if args.command == "verify":
            report = verify(args.rounds)
            output = ROOT / "data/oscar-verification.json"
            output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(f"Verification report: {output}")
        else:
            print(
                "IncidentLab: http://127.0.0.1:8100\nOscar shop: http://127.0.0.1:8200/en-gb/catalogue/\nCtrl+C stops both.",
                flush=True,
            )
            while True:
                lab.check()
                if process.poll() is not None:
                    raise RuntimeError("Oscar exited; inspect data/oscar-shop.log")
                time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped the local shop and collector.")
