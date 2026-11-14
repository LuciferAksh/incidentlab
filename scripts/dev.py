"""Cross-platform local process supervisor. No Docker required."""

import argparse
import contextlib
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent


def check_port(port: int):
    with socket.socket() as sock:
        # Match uvicorn's POSIX reuse behavior: TIME_WAIT is not a live listener.
        # On Windows SO_REUSEADDR can permit overlapping listeners, so keep its
        # exclusive default behavior there instead.
        if os.name != "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(
                f"Port {port} is already in use. Stop the other process before starting IncidentLab."
            ) from exc


class RunningLab:
    def __init__(self, python: str = sys.executable, db_path: str | None = None, external: bool = False):
        self.python = python
        self.db_path = db_path
        self.external = external
        self.children: list[subprocess.Popen] = []
        self.logs = contextlib.ExitStack()

    def __enter__(self):
        ports = [8100] if self.external else list(range(8100, 8104))
        for port in ports:
            check_port(port)
        env = {**os.environ, "LAB_CONTROL_TOKEN": secrets.token_urlsafe(32), "PYTHONUNBUFFERED": "1"}
        env["LAB_MODE"] = "external" if self.external else "demo"
        if self.db_path:
            env["LAB_DB_PATH"] = self.db_path
        (ROOT / "data").mkdir(exist_ok=True)
        try:
            processes = (
                [("api", 8100)]
                if self.external
                else [("inventory", 8102), ("payments", 8103), ("checkout", 8101), ("api", 8100)]
            )
            for name, port in processes:
                log = self.logs.enter_context((ROOT / "data" / f"{name}.log").open("a", encoding="utf-8"))
                factory = (
                    "incidentlab.api:create_app" if name == "api" else "incidentlab.services:create_service"
                )
                command = [
                    self.python,
                    "-m",
                    "uvicorn",
                    factory,
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                ]
                child = subprocess.Popen(
                    command, cwd=ROOT, env={**env, "LAB_SERVICE": name}, stdout=log, stderr=log
                )
                self.children.append(child)
                # Readiness, not process creation, is the dependency boundary.
                ready_deadline = time.monotonic() + 20
                while time.monotonic() < ready_deadline:
                    self.check()
                    try:
                        endpoint = "api/health" if name == "api" else "health"
                        with urlopen(f"http://127.0.0.1:{port}/{endpoint}", timeout=1) as response:
                            if response.status == 200:
                                break
                    except (URLError, TimeoutError, ConnectionError):
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"{name} did not become ready. Inspect data/{name}.log.")
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                self.check()
                try:
                    for port in ports:
                        with urlopen(
                            f"http://127.0.0.1:{port}/{'api/health' if port == 8100 else 'health'}", timeout=1
                        ) as response:
                            if response.status != 200:
                                raise RuntimeError("Service not ready")
                    return self
                except (URLError, TimeoutError, ConnectionError):
                    time.sleep(0.2)
            raise RuntimeError("Services did not become ready. Inspect data/*.log.")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def check(self):
        for child in self.children:
            if child.poll() is not None:
                raise RuntimeError(
                    f"Service process {child.pid} exited ({child.returncode}). Inspect data/*.log."
                )

    def __exit__(self, *_):
        # Stop API first so its recovery shutdown can reach all service processes.
        for child in reversed(self.children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
        self.logs.close()


def interpreter() -> str:
    local = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(local) if local.exists() else sys.executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-build", action="store_true", help="Use the existing dashboard build")
    parser.add_argument(
        "--external",
        action="store_true",
        help="Collector only: observe an independently instrumented application",
    )
    args = parser.parse_args()
    os.chdir(ROOT)
    if not args.no_build:
        npm = "npm.cmd" if os.name == "nt" else "npm"
        subprocess.run([npm, "run", "build"], check=True)
    elif not (ROOT / "web/dist/index.html").exists():
        raise SystemExit("Dashboard missing. Run npm run build first.")
    if os.name != "nt":
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        with RunningLab(interpreter(), external=args.external) as lab:
            print("\nIncidentLab is running at http://127.0.0.1:8100", flush=True)
            print("API reference: http://127.0.0.1:8100/docs", flush=True)
            print(
                "External mode: capture a healthy application baseline."
                if args.external
                else "Warming built-in service baseline.",
                flush=True,
            )
            print("Logs: data/*.log. Press Ctrl+C to stop.\n", flush=True)
            while True:
                lab.check()
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nIncidentLab stopped.")


if __name__ == "__main__":
    main()
