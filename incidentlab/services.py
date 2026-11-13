"""Three actual HTTP services, with bounded, authenticated local fault controls."""

import asyncio
import hmac
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import FastAPI, Header, HTTPException
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel

from incidentlab.telemetry import call, install_middleware, setup


class Fault(BaseModel):
    mode: Literal["healthy", "latency", "errors"] = "healthy"


def create_service(service: str | None = None) -> FastAPI:
    name = service or os.getenv("LAB_SERVICE", "checkout")
    if name not in {"checkout", "inventory", "payments"}:
        raise ValueError(f"Unknown service: {name}")
    token = os.environ.get("LAB_CONTROL_TOKEN")
    if not token:
        raise RuntimeError("LAB_CONTROL_TOKEN must be set; use python scripts/dev.py")
    provider = setup(name)
    tracer = trace.get_tracer(f"incidentlab.{name}")
    fault = Fault()

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            app.state.client = client
            yield
        provider.shutdown()

    # FastAPI 0.162+ instruments requests itself when an OTel provider is present.
    # Our explicit boundary spans own propagation; a second middleware would double-count requests.
    app = FastAPI(title=f"IncidentLab / {name}", lifespan=lifespan, telemetry={"tracing": False})
    install_middleware(app, tracer)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": name}

    @app.post("/control")
    async def control(body: Fault, x_lab_token: str = Header(default="")):
        if not hmac.compare_digest(x_lab_token, token):
            raise HTTPException(403, "Invalid control token")
        fault.mode = body.mode
        return {"service": name, "mode": fault.mode}

    @app.get("/request")
    async def request():
        mode = fault.mode  # Each request observes one consistent fault state.
        if mode == "errors":
            span = trace.get_current_span()
            span.add_event(
                "request.failed", {"error.type": "ServiceUnavailable", "message": "dependency unavailable"}
            )
            span.set_status(Status(StatusCode.ERROR))
            raise HTTPException(503, "Service temporarily unavailable")
        if name == "inventory":
            with tracer.start_as_current_span("SELECT inventory", attributes={"db.system.name": "sqlite"}):
                # The delay runs inside a real SQL operation, on a worker thread.
                def query():
                    with sqlite3.connect(":memory:") as db:
                        db.create_function("lab_delay", 1, lambda seconds: (time.sleep(seconds), 0)[1])
                        return db.execute(
                            "SELECT 42 AS stock, lab_delay(?)", (0.35 if mode == "latency" else 0.008,)
                        ).fetchone()[0]

                stock = await asyncio.to_thread(query)
            return {"stock": stock}
        if name == "payments":
            await asyncio.sleep(0.25 if mode == "latency" else 0.012)
            return {"authorized": True}
        await asyncio.sleep(0.35 if mode == "latency" else 0.006)
        for target, default in [
            ("inventory", "http://127.0.0.1:8102"),
            ("payments", "http://127.0.0.1:8103"),
        ]:
            url = os.getenv(f"LAB_{target.upper()}_URL", default)
            try:
                response = await call(app.state.client, tracer, target, f"{url}/request")
            except httpx.RequestError as exc:
                trace.get_current_span().add_event(
                    "dependency.failed", {"error.type": type(exc).__name__, "dependency": target}
                )
                raise HTTPException(502, f"{target} unreachable") from exc
            if response.is_error:
                raise HTTPException(502, f"{target} returned {response.status_code}")
        return {"order": "accepted"}

    return app
