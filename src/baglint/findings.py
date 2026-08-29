"""Findings are the tool's output contract.

Every check emits these and nothing else. The ``code`` field is the stable,
machine-readable identity of a finding -- CI configs filter and baseline on it,
so treat these strings as public API and never repurpose one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Level(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    FAIL = "FAIL"


class Clock(str, Enum):
    """Which of a bag's two clocks a finding was measured against.

    A gap in LOG means the recorder stalled; a gap in HEADER means the sensor
    or its driver misbehaved. Conflating them is the classic bug in homegrown
    bag scripts, so every finding states which one it used.
    """

    LOG = "log_time"
    HEADER = "header.stamp"


@dataclass(frozen=True)
class Finding:
    level: Level
    code: str
    message: str
    topic: str | None = None
    clock: Clock | None = None
    t_start: float | None = None
    t_end: float | None = None
    # Excluded from eq/hash: a frozen dataclass derives __hash__ from its
    # compared fields, and a dict field would make every Finding unhashable.
    # A finding's identity is its level, code, topic, clock and time span.
    details: dict[str, Any] = field(default_factory=dict, compare=False)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "level": self.level.value,
            "code": self.code,
            "message": self.message,
        }
        if self.topic is not None:
            out["topic"] = self.topic
        if self.clock is not None:
            out["clock"] = self.clock.value
        if self.t_start is not None:
            out["t_start"] = round(self.t_start, 6)
        if self.t_end is not None:
            out["t_end"] = round(self.t_end, 6)
        if self.details:
            out["details"] = self.details
        return out
