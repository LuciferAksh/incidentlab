"""Baseline/analysis sessions for independently instrumented applications."""

import time
import uuid

from pydantic import BaseModel, Field, model_validator

from incidentlab.diagnosis import diagnose, groups, summarize
from incidentlab.models import Span
from incidentlab.store import Store


class Window(BaseModel):
    start: float = Field(allow_inf_nan=False)
    end: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_window(self):
        now = time.time()
        if not now - 86400 <= self.start < self.end <= now + 5:
            raise ValueError("Use a completed observation window within the last 24 hours")
        if self.end - self.start > 3600:
            raise ValueError("Observation windows are limited to one hour")
        return self


class BaselineRequest(Window):
    name: str = Field(min_length=1, max_length=100)
    services: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def valid_services(self):
        if any(not s.strip() or len(s) > 120 for s in self.services) or len(set(self.services)) != len(
            self.services
        ):
            raise ValueError("Service names must be nonempty and unique")
        return self


class AnalysisRequest(Window):
    baseline_id: str = Field(min_length=1, max_length=32)
    title: str = Field(default="External application analysis", min_length=1, max_length=120)


def baseline_summary(baseline: dict) -> dict:
    return {key: value for key, value in baseline.items() if key != "spans"}


def capture(store: Store, body: BaselineRequest) -> dict:
    spans = [s for s in store.window(body.start, body.end) if s.service in body.services]
    samples = groups(spans)
    missing = [s for s in body.services if len(samples.get(s, [])) < 5]
    if missing:
        raise ValueError(
            f"At least 5 server spans are required per service; insufficient samples: {', '.join(missing)}"
        )
    baseline = {
        "id": uuid.uuid4().hex[:16],
        "created_at": time.time(),
        "name": body.name,
        "start": body.start,
        "end": body.end,
        "services": body.services,
        "summary": summarize(spans),
        "span_count": len(spans),
        "spans": [s.model_dump() for s in spans],
    }
    store.save_baseline(baseline)
    return baseline


def analyse(store: Store, body: AnalysisRequest) -> dict:
    baseline = next((b for b in store.baselines() if b["id"] == body.baseline_id), None)
    if baseline is None:
        raise LookupError("Baseline not found")
    if body.start < baseline["end"]:
        raise ValueError("Analysis must start after the baseline window ends")
    current = [s for s in store.window(body.start, body.end) if s.service in baseline["services"]]
    normal = [Span.model_validate(s) for s in baseline["spans"]]
    result = diagnose(current, normal)
    samples = groups(current)
    missing = [s for s in baseline["services"] if len(samples.get(s, [])) < 5]
    if missing:
        result["caveats"].append(f"Insufficient current samples for expected services: {', '.join(missing)}")
        if result["status"] == "healthy":
            result["status"] = "insufficient_data"
    incident = {
        "id": uuid.uuid4().hex[:16],
        "created_at": body.start,
        "ended_at": body.end,
        "title": body.title,
        "scenario_id": "external",
        "source": "external",
        "baseline_id": baseline["id"],
        "diagnosis": result,
        "services": summarize(current),
        "ground_truth": None,
        "top1_correct": None,
        "trace_count": len({s.trace_id for s in current}),
        "duration_seconds": round(body.end - body.start, 2),
        "timeline": [
            {"at": baseline["created_at"], "message": f"Baseline captured: {baseline['name']}"},
            {"at": body.start, "message": "External observation window started"},
            {"at": time.time(), "message": "Evidence ranking completed; no fault labels supplied"},
        ],
    }
    store.save_incident(incident)
    return incident
