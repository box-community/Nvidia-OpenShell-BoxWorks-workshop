from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Trace:
    trace_id: str = field(default_factory=lambda: f"trace-{uuid.uuid4().hex[:10]}")
    events: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, **data: Any) -> None:
        self.events.append({"name": name, "time": time.time(), **data})

    def as_dict(self) -> dict[str, Any]:
        return {"trace_id": self.trace_id, "events": self.events}
