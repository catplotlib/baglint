from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from baglint.findings import Finding
from baglint.reader import Message
from baglint.spec import Spec


@dataclass
class TopicStat:
    """Per-topic timing, accumulated by the runner for every topic in the bag."""

    topic: str
    count: int = 0
    first_ns: int | None = None
    last_ns: int | None = None
    max_interval_ns: int = 0

    def observe(self, log_time_ns: int) -> None:
        if self.first_ns is None:
            self.first_ns = log_time_ns
        else:
            self.max_interval_ns = max(self.max_interval_ns, log_time_ns - self.last_ns)
        self.last_ns = log_time_ns
        self.count += 1

    @property
    def max_interval_ms(self) -> float:
        return self.max_interval_ns / 1e6

    @property
    def span_s(self) -> float:
        if self.first_ns is None or self.last_ns is None:
            return 0.0
        return (self.last_ns - self.first_ns) / 1e9

    @property
    def rate_hz(self) -> float | None:
        """Mean rate over the topic's own span.

        Uses count-1 intervals rather than count messages: for N evenly spaced
        messages there are N-1 gaps, and dividing by N biases the rate low on
        short recordings.
        """
        if self.count < 2 or self.span_s <= 0:
            return None
        return (self.count - 1) / self.span_s


@dataclass
class RunContext:
    spec: Spec
    stats: dict[str, TopicStat] = field(default_factory=dict)
    start_ns: int = 0
    end_ns: int = 0

    @property
    def duration_s(self) -> float:
        return max(0.0, (self.end_ns - self.start_ns) / 1e9)

    def rel_s(self, ns: int) -> float:
        """Seconds since the first message in the bag."""
        return (ns - self.start_ns) / 1e9


class Check(Protocol):
    """A streaming accumulator.

    Checks see every message once, in log_time order, then report at the end.
    ``wants_decoded`` names the topics whose payloads must be deserialized;
    keep it empty unless the check actually reads message fields.
    """

    wants_decoded: frozenset[str]

    def on_message(self, msg: Message) -> None: ...

    def finalize(self, ctx: RunContext) -> list[Finding]: ...
