from typing import Any

from pydantic import BaseModel, Field


class Span(BaseModel):
    trace_id: str
    span_id: str
    parent_id: str = ""
    service: str
    name: str
    kind: int = 1
    start_ns: int
    end_ns: int
    error: bool = False
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        return max(0, self.end_ns - self.start_ns) / 1_000_000
