"""header.stamp integrity.

Unlike the other checks, this one reads message payloads, so it is opt-in per
topic via the spec's ``check_stamps`` key.

A stamp that moves backwards is the serious case: tf2, message_filters and the
SLAM backends downstream all assume a non-decreasing stamp sequence per topic,
and none of them report the violation. Duplicate and unset stamps are recorded
as warnings, since they degrade interpolation without breaking it outright.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from baglint.checks.base import RunContext
from baglint.findings import Clock, Finding, Level
from baglint.reader import Message
from baglint.spec import Spec


@dataclass
class _TopicState:
    previous_ns: int | None = None
    backwards: list[tuple[int, int]] = field(default_factory=list)  # (log_time, regression_ns)
    duplicates: int = 0
    unset: int = 0
    header_missing: bool = False


def _stamp_ns(decoded) -> int | None:
    """Nanoseconds from a std_msgs/Header stamp, or None when absent."""
    header = getattr(decoded, "header", None)
    stamp = getattr(header, "stamp", None)
    if stamp is None:
        return None
    sec = getattr(stamp, "sec", None)
    nanosec = getattr(stamp, "nanosec", None)
    if sec is None or nanosec is None:
        return None
    return sec * 1_000_000_000 + nanosec


class StampCheck:
    def __init__(self, spec: Spec):
        self._spec = spec
        self._states: dict[str, _TopicState] = {}

    def decode_topics(self, topics: Iterable[str]) -> set[str]:
        enabled = set()
        for topic in topics:
            ts = self._spec.for_topic(topic)
            if ts is not None and ts.check_stamps:
                enabled.add(topic)
        return enabled

    def on_message(self, msg: Message) -> None:
        if msg.decoded is None:
            return

        state = self._states.get(msg.topic)
        if state is None:
            state = self._states[msg.topic] = _TopicState()

        stamp = _stamp_ns(msg.decoded)
        if stamp is None:
            state.header_missing = True
            return

        # A zero stamp was never populated, so it says nothing about ordering
        # and must not become the baseline for the messages that follow.
        if stamp == 0:
            state.unset += 1
            return

        if state.previous_ns is not None:
            if stamp < state.previous_ns:
                state.backwards.append((msg.log_time_ns, state.previous_ns - stamp))
            elif stamp == state.previous_ns:
                state.duplicates += 1

        state.previous_ns = stamp

    def finalize(self, ctx: RunContext) -> list[Finding]:
        findings = []
        for topic, state in sorted(self._states.items()):
            if state.header_missing:
                findings.append(
                    Finding(
                        level=Level.WARN,
                        code="stamp_unavailable",
                        topic=topic,
                        message="check_stamps is set but the message type has no header.stamp",
                    )
                )

            if state.backwards:
                worst_log_ns, worst_ns = max(state.backwards, key=lambda b: b[1])
                findings.append(
                    Finding(
                        level=Level.FAIL,
                        code="stamp_backwards",
                        topic=topic,
                        clock=Clock.HEADER,
                        message=(
                            f"{len(state.backwards)} stamp(s) moved backwards "
                            f"(worst {worst_ns / 1e6:.1f} ms at {ctx.rel_s(worst_log_ns):.2f} s)"
                        ),
                        t_start=ctx.rel_s(state.backwards[0][0]),
                        t_end=ctx.rel_s(state.backwards[-1][0]),
                        details={
                            "count": len(state.backwards),
                            "worst_ms": round(worst_ns / 1e6, 3),
                        },
                    )
                )

            if state.duplicates:
                findings.append(
                    Finding(
                        level=Level.WARN,
                        code="stamp_duplicate",
                        topic=topic,
                        clock=Clock.HEADER,
                        message=f"{state.duplicates} message(s) repeated the previous stamp",
                        details={"count": state.duplicates},
                    )
                )

            if state.unset:
                findings.append(
                    Finding(
                        level=Level.WARN,
                        code="stamp_unset",
                        topic=topic,
                        clock=Clock.HEADER,
                        message=f"{state.unset} message(s) carried a zero stamp",
                        details={"count": state.unset},
                    )
                )
        return findings
