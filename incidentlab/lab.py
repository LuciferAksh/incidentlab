import asyncio
import contextlib
import os
import time
import uuid

import httpx

from incidentlab.diagnosis import diagnose, groups
from incidentlab.store import Store

SCENARIOS = [
    {
        "id": "inventory-latency",
        "name": "Slow database",
        "service": "inventory",
        "mode": "latency",
        "description": "Add 350 ms inside an inventory SQL operation. Watch latency propagate to checkout.",
        "category": "Latency",
    },
    {
        "id": "payment-errors",
        "name": "Payment outage",
        "service": "payments",
        "mode": "errors",
        "description": "Return 503 from payments and follow the cascading checkout failures.",
        "category": "Availability",
    },
    {
        "id": "inventory-errors",
        "name": "Inventory outage",
        "service": "inventory",
        "mode": "errors",
        "description": "Fail inventory requests before payment processing can begin.",
        "category": "Availability",
    },
    {
        "id": "checkout-latency",
        "name": "Checkout regression",
        "service": "checkout",
        "mode": "latency",
        "description": "Slow local checkout processing while its dependencies remain healthy.",
        "category": "Latency",
    },
    {
        "id": "healthy",
        "name": "Healthy control",
        "service": None,
        "mode": "healthy",
        "description": "Run the same experiment without a fault to check for false alarms.",
        "category": "Control",
    },
]


class Lab:
    def __init__(self, store: Store):
        self.store = store
        self.lock = asyncio.Lock()
        self.experiment: asyncio.Task | None = None
        self.baseline = []
        self.status = {"phase": "warming", "message": "Waiting for the service lab", "scenario": None}
        self.client = httpx.AsyncClient(timeout=4, trust_env=False)
        self.urls = {
            name: os.getenv(f"LAB_{name.upper()}_URL", f"http://127.0.0.1:{port}")
            for name, port in [("checkout", 8101), ("inventory", 8102), ("payments", 8103)]
        }
        self.token = os.getenv("LAB_CONTROL_TOKEN", "")
        self.traffic = None

    async def start(self):
        self.traffic = asyncio.create_task(self._background())

    async def close(self):
        for task in [self.traffic, self.experiment]:
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        with contextlib.suppress(Exception):
            await self.reset()
        await self.client.aclose()

    async def reset(self):
        results = await asyncio.gather(
            *[
                self.client.post(
                    f"{url}/control", json={"mode": "healthy"}, headers={"x-lab-token": self.token}
                )
                for url in self.urls.values()
            ],
            return_exceptions=True,
        )
        failed = [
            name
            for name, response in zip(self.urls, results, strict=True)
            if isinstance(response, Exception) or response.status_code != 200
        ]
        if failed:
            raise RuntimeError(f"Could not reset services: {', '.join(failed)}")

    async def load(self, count: int):
        semaphore = asyncio.Semaphore(3)

        async def one():
            async with semaphore:
                # HTTP failures are expected evidence, but network failures abort the experiment.
                await self.client.get(f"{self.urls['checkout']}/request")

        await asyncio.gather(*(one() for _ in range(count)))
        await asyncio.sleep(0.5)  # Allow the SDK batch exporter to flush completed spans.

    async def _background(self):
        warming_since = time.monotonic()
        while True:
            try:
                if not self.baseline:
                    async with self.lock:
                        await self.reset()
                        start = time.time()
                        await self.load(24)
                        candidate = self.store.window(start, time.time())
                        observed = groups(candidate)
                        if any(len(observed.get(service, [])) < 5 for service in self.urls):
                            raise RuntimeError(
                                "Waiting for complete baseline telemetry from all three services"
                            )
                        self.baseline = candidate
                        self.status = {
                            "phase": "idle",
                            "message": "Live traffic is flowing",
                            "scenario": None,
                        }
                async with self.lock:
                    await self.client.get(f"{self.urls['checkout']}/request")
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                phase = "warming" if not self.baseline and time.monotonic() - warming_since < 30 else "error"
                self.status = {"phase": phase, "message": str(exc), "scenario": None}
                await asyncio.sleep(3)

    def launch(self, scenario_id: str) -> str:
        if not self.baseline:
            raise RuntimeError("The lab is still warming up. Check service health and try again.")
        if self.experiment and not self.experiment.done():
            raise RuntimeError("An experiment is already running")
        scenario = next(s for s in SCENARIOS if s["id"] == scenario_id)
        run_id = uuid.uuid4().hex[:12]
        self.status = {
            "phase": "baseline",
            "message": "Measuring a fresh healthy baseline",
            "scenario": scenario_id,
            "run_id": run_id,
        }
        self.experiment = asyncio.create_task(self._run(scenario, run_id))
        return run_id

    async def _run(self, scenario: dict, run_id: str):
        async with self.lock:
            timeline = []
            incident = None

            def event(message: str):
                timeline.append({"at": time.time(), "message": message})

            try:
                await self.reset()
                start = time.time()
                event("Healthy baseline collection started")
                await self.load(24)
                baseline = self.store.window(start, time.time())
                self.baseline = baseline
                if scenario["service"]:
                    response = await self.client.post(
                        f"{self.urls[scenario['service']]}/control",
                        json={"mode": scenario["mode"]},
                        headers={"x-lab-token": self.token},
                    )
                    response.raise_for_status()
                current_start = time.time()
                event("Experiment window started")
                self.status = {
                    **self.status,
                    "phase": "observing",
                    "message": "Collecting 30 requests under experiment conditions",
                }
                await self.load(30)
                current_end = time.time()
                current = self.store.window(current_start, current_end)
                # IMPORTANT: only spans cross this boundary. Ground truth is attached AFTER diagnosis.
                result = diagnose(current, baseline)
                event("Evidence ranking completed")
                from incidentlab.diagnosis import summarize

                incident = {
                    "id": run_id,
                    "created_at": current_start,
                    "ended_at": current_end,
                    "title": scenario["name"],
                    "scenario_id": scenario["id"],
                    "diagnosis": result,
                    "services": summarize(current),
                    "ground_truth": scenario["service"],
                    "top1_correct": (
                        result["suspects"][0]["service"] == scenario["service"]
                        if result["suspects"]
                        else scenario["service"] is None and result["status"] == "healthy"
                    ),
                    "timeline": timeline,
                    "trace_count": len({s.trace_id for s in current}),
                    "duration_seconds": round(current_end - current_start, 2),
                }
                self.store.save_incident(incident)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.status = {**self.status, "phase": "error", "message": f"Experiment failed: {exc}"}
            finally:
                try:
                    await self.reset()
                    if incident:
                        event("Fault removed; services restored")
                        self.store.save_incident(incident)
                        self.status = {
                            "phase": "idle",
                            "message": "Experiment complete. Healthy traffic restored.",
                            "scenario": None,
                            "last_run_id": run_id,
                        }
                except Exception as exc:
                    self.status = {
                        **self.status,
                        "phase": "error",
                        "message": f"Recovery failed: {exc}. Restart the lab before another experiment.",
                    }
