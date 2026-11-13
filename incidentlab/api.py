import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from google.protobuf.message import DecodeError
from pydantic import BaseModel

from incidentlab.diagnosis import diagnose, summarize, topology
from incidentlab.lab import SCENARIOS, Lab
from incidentlab.otlp import decode
from incidentlab.store import Store


class ExperimentRequest(BaseModel):
    scenario: Literal[
        "inventory-latency", "payment-errors", "inventory-errors", "checkout-latency", "healthy"
    ]


def create_app(store: Store | None = None, run_lab: bool = True) -> FastAPI:
    database = store or Store(os.getenv("LAB_DB_PATH", "data/incidentlab.db"))
    lab = Lab(database)

    @asynccontextmanager
    async def lifespan(app):
        if run_lab:
            await lab.start()
        yield
        if run_lab:
            await lab.close()
        else:
            await lab.client.aclose()
        if store is None:
            database.close()

    app = FastAPI(title="IncidentLab", version="0.1.0", lifespan=lifespan, telemetry={"tracing": False})
    app.state.store = database
    app.state.lab = lab

    @app.middleware("http")
    async def guard_mutations(request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            # Browser-driven local controls reject cross-origin mutations. OTLP SDKs send no Origin.
            origin = request.headers.get("origin")
            allowed = {str(request.base_url).rstrip("/"), "http://127.0.0.1:5173", "http://localhost:5173"}
            if origin and origin not in allowed:
                return Response("Cross-origin mutation rejected", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "0.1.0", "lab": lab.status}

    @app.post("/v1/traces")
    async def ingest(request: Request):
        if request.headers.get("content-type", "").split(";")[0] != "application/x-protobuf":
            raise HTTPException(415, "Expected OTLP protobuf; compressed bodies are not supported")
        if request.headers.get("content-encoding"):
            raise HTTPException(415, "Compressed bodies are not supported")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 2 * 1024 * 1024:
                raise HTTPException(413, "OTLP request exceeds 2 MiB")
        try:
            spans = decode(bytes(body))
        except (DecodeError, ValueError) as exc:
            raise HTTPException(400, "Invalid OTLP trace payload") from exc
        database.insert(spans)
        return Response(b"", media_type="application/x-protobuf")

    @app.get("/api/overview")
    async def overview():
        now = time.time()
        spans = database.window(now - 60, now)
        services = summarize(spans)
        roots = [s for s in spans if s.kind == 2 and not s.parent_id]
        buckets = []
        for offset in range(12):
            start = now - 60 + offset * 5
            rows = [s for s in roots if start <= s.start_ns / 1e9 < start + 5]
            from incidentlab.diagnosis import percentile

            buckets.append(
                {
                    "at": start,
                    "requests": len(rows),
                    "errors": sum(s.error for s in rows),
                    "p95_ms": round(percentile([s.duration_ms for s in rows], 0.95), 1),
                }
            )
        incidents = database.incidents()
        return {
            "now": now,
            "window_seconds": 60,
            "lab": lab.status,
            "services": services,
            "topology": topology(spans),
            "series": buckets,
            "request_count": len(roots),
            "span_count": len(spans),
            "error_rate": sum(s.error for s in roots) / len(roots) if roots else 0,
            "diagnosis": diagnose(spans, lab.baseline),
            "incidents": [{k: v for k, v in i.items() if k not in {"timeline"}} for i in incidents],
            "metric_source": "Derived from collected server spans; not an independent metrics pipeline",
        }

    @app.get("/api/scenarios")
    async def scenarios():
        return SCENARIOS

    @app.post("/api/experiments", status_code=202)
    async def experiment(body: ExperimentRequest):
        try:
            run_id = lab.launch(body.scenario)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"run_id": run_id, "status": "accepted"}

    @app.get("/api/incidents/{incident_id}")
    async def incident(incident_id: str):
        found = next((i for i in database.incidents() if i["id"] == incident_id), None)
        if found is None:
            raise HTTPException(404, "Incident not found")
        return found

    @app.get("/api/traces")
    async def traces():
        spans = database.window(time.time() - 3600, time.time(), limit=10000)
        roots = sorted(
            [s for s in spans if s.kind == 2 and not s.parent_id], key=lambda s: s.start_ns, reverse=True
        )
        return [
            {
                "trace_id": s.trace_id,
                "service": s.service,
                "name": s.name,
                "start_ns": s.start_ns,
                "duration_ms": round(s.duration_ms, 2),
                "error": s.error,
            }
            for s in roots[:60]
        ]

    @app.get("/api/traces/{trace_id}")
    async def get_trace(trace_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", trace_id):
            raise HTTPException(422, "Expected a 32-character lowercase hexadecimal trace ID")
        spans = database.trace(trace_id)
        if not spans:
            raise HTTPException(404, "Trace not found or outside retention")
        return [dict(s.model_dump(), duration_ms=round(s.duration_ms, 3)) for s in spans]

    @app.get("/api/report")
    async def report():
        incidents = database.incidents()
        fault_runs = [i for i in incidents if i["ground_truth"]]
        controls = [i for i in incidents if not i["ground_truth"]]
        return {
            "runs": len(incidents),
            "fault_runs": len(fault_runs),
            "control_runs": len(controls),
            "top1_accuracy": sum(i["top1_correct"] for i in fault_runs) / len(fault_runs)
            if fault_runs
            else None,
            "control_false_positive_rate": sum(i["diagnosis"]["status"] == "incident" for i in controls)
            / len(controls)
            if controls
            else None,
            "scope": "Local injected scenarios only. This is not an independent production benchmark.",
            "incidents": incidents,
        }

    dist = Path(__file__).resolve().parent.parent / "web" / "dist"
    if dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        async def index():
            return FileResponse(dist / "index.html")

    return app
