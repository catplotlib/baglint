from __future__ import annotations

from collections import defaultdict

from baglint.checks.base import RunContext
from baglint.findings import Clock, Finding, Level
from baglint.reader import Message
from baglint.spec import Spec


class GapCheck:
    """Finds recording dropouts: consecutive messages on a topic further apart
    than the spec's max_gap_ms.

    Measured on log_time, so a finding here means the recorder stalled, not
    that the sensor did. Gaps are only ever measured between two messages of
    the same topic, which is what keeps a late-starting or early-ending topic
    from reporting a spurious gap against the bag's own boundaries.
    """

    wants_decoded = frozenset()

    def __init__(self, spec: Spec):
        self._spec = spec
        self._last: dict[str, int] = {}
        self._gaps: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self._thresholds: dict[str, float | None] = {}

    def _threshold_ns(self, topic: str) -> float | None:
        if topic not in self._thresholds:
            ts = self._spec.for_topic(topic)
            ms = ts.max_gap_ms if ts else None
            self._thresholds[topic] = None if ms is None else ms * 1e6
        return self._thresholds[topic]

    def on_message(self, msg: Message) -> None:
        threshold = self._threshold_ns(msg.topic)
        if threshold is None:
            return
        previous = self._last.get(msg.topic)
        if previous is not None and (msg.log_time_ns - previous) > threshold:
            self._gaps[msg.topic].append((previous, msg.log_time_ns))
        self._last[msg.topic] = msg.log_time_ns

    def finalize(self, ctx: RunContext) -> list[Finding]:
        findings = []
        for topic, gaps in sorted(self._gaps.items()):
            threshold_ms = self._thresholds[topic] / 1e6
            intervals = [
                {
                    "start": round(ctx.rel_s(a), 6),
                    "end": round(ctx.rel_s(b), 6),
                    "gap_ms": round((b - a) / 1e6, 3),
                }
                for a, b in gaps
            ]
            worst = max(intervals, key=lambda i: i["gap_ms"])
            findings.append(
                Finding(
                    level=Level.FAIL,
                    code="gap",
                    topic=topic,
                    clock=Clock.LOG,
                    message=(
                        f"{len(gaps)} missing interval(s) >{threshold_ms:g} ms "
                        f"(worst {worst['gap_ms']:.1f} ms at {worst['start']:.2f} s)"
                    ),
                    t_start=intervals[0]["start"],
                    t_end=intervals[-1]["end"],
                    details={
                        "threshold_ms": threshold_ms,
                        "count": len(gaps),
                        "worst_ms": worst["gap_ms"],
                        "intervals": intervals,
                    },
                )
            )
        return findings
