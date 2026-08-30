"""Transform availability over time.

Every other check is a per-topic scalar. This one is a graph that changes as
the recording plays, and the question it answers is whether a path existed
between two frames at a given moment, not whether a topic behaved.

Availability is computed per edge, then intersected along a path. Because the
tree can be rewired mid-recording, connectivity is evaluated by sweeping the
interval boundaries: between two consecutive boundaries the set of live edges
is constant, so a plain search over that set answers the question exactly.

Transform validity is measured on header.stamp, which is the time a transform
describes, rather than on when the recorder happened to write it.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable

from baglint.checks.base import RunContext
from baglint.findings import Clock, Finding, Level
from baglint.reader import Message
from baglint.spec import Spec

TF_TOPIC = "/tf"
TF_STATIC_TOPIC = "/tf_static"

Edge = tuple[str, str]
Interval = tuple[float, float]


@dataclass
class _EdgeRecord:
    stamps: list[float] = field(default_factory=list)
    static: bool = False


def _merge_stamps(stamps: list[float], max_stale_s: float) -> list[Interval]:
    """Turn a sequence of update times into the spans the edge was usable.

    An edge is usable from one update to the next, and for max_stale_s after
    its last one. Ending validity exactly at the final update would report a
    gap whenever transforms stop marginally before the recording does.
    """
    if not stamps:
        return []

    ordered = sorted(stamps)
    intervals = []
    start = previous = ordered[0]

    for stamp in ordered[1:]:
        if stamp - previous > max_stale_s:
            intervals.append((start, previous + max_stale_s))
            start = stamp
        previous = stamp

    intervals.append((start, previous + max_stale_s))
    return intervals


def _covers(intervals: list[Interval], instant: float) -> bool:
    return any(start <= instant <= end for start, end in intervals)


def _connected(edges: Iterable[Edge], source: str, target: str) -> bool:
    """Frames are reachable in either direction, since a transform can be
    inverted."""
    adjacency: dict[str, list[str]] = defaultdict(list)
    for parent, child in edges:
        adjacency[parent].append(child)
        adjacency[child].append(parent)

    if source not in adjacency or target not in adjacency:
        return False

    seen = {source}
    queue = deque([source])
    while queue:
        frame = queue.popleft()
        if frame == target:
            return True
        for neighbour in adjacency[frame]:
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return False


class TfCheck:
    def __init__(self, spec: Spec):
        self._spec = spec
        self._edges: dict[Edge, _EdgeRecord] = defaultdict(_EdgeRecord)

    def decode_topics(self, topics: Iterable[str]) -> set[str]:
        if not self._spec.required_transforms:
            return set()
        return {t for t in topics if t in (TF_TOPIC, TF_STATIC_TOPIC)}

    def on_message(self, msg: Message) -> None:
        if msg.decoded is None or msg.topic not in (TF_TOPIC, TF_STATIC_TOPIC):
            return

        for transform in getattr(msg.decoded, "transforms", ()) or ():
            header = getattr(transform, "header", None)
            parent = getattr(header, "frame_id", None)
            child = getattr(transform, "child_frame_id", None)
            if not parent or not child:
                continue

            record = self._edges[(parent, child)]
            if msg.topic == TF_STATIC_TOPIC:
                # Latched: published once, valid for the whole recording.
                record.static = True
                continue

            stamp = getattr(header, "stamp", None)
            if stamp is None:
                continue
            record.stamps.append(
                getattr(stamp, "sec", 0) + getattr(stamp, "nanosec", 0) / 1e9
            )

    def _availability(self, ctx: RunContext) -> dict[Edge, list[Interval]]:
        max_stale_s = self._spec.transform_max_stale_ms / 1000.0
        span = (ctx.start_ns / 1e9, ctx.end_ns / 1e9)

        availability = {}
        for edge, record in self._edges.items():
            if record.static:
                availability[edge] = [span]
            else:
                availability[edge] = _merge_stamps(record.stamps, max_stale_s)
        return availability

    def _unavailable(self, ctx: RunContext, source: str, target: str) -> list[Interval]:
        """Spans where no path connected the two frames."""
        availability = self._availability(ctx)
        recording = (ctx.start_ns / 1e9, ctx.end_ns / 1e9)

        boundaries = {recording[0], recording[1]}
        for intervals in availability.values():
            for start, end in intervals:
                boundaries.update((start, end))
        ordered = sorted(b for b in boundaries if recording[0] <= b <= recording[1])

        if len(ordered) < 2:
            return [recording] if not _connected(availability, source, target) else []

        missing: list[Interval] = []
        for left, right in zip(ordered, ordered[1:]):
            if right <= left:
                continue
            midpoint = (left + right) / 2
            live = [e for e, iv in availability.items() if _covers(iv, midpoint)]
            if not _connected(live, source, target):
                if missing and abs(missing[-1][1] - left) < 1e-9:
                    missing[-1] = (missing[-1][0], right)
                else:
                    missing.append((left, right))
        return missing

    def finalize(self, ctx: RunContext) -> list[Finding]:
        if not self._spec.required_transforms:
            return []

        origin = ctx.start_ns / 1e9
        findings = []

        for source, target in self._spec.required_transforms:
            known = {frame for edge in self._edges for frame in edge}
            if source not in known or target not in known:
                absent = [f for f in (source, target) if f not in known]
                findings.append(
                    Finding(
                        level=Level.FAIL,
                        code="tf_frame_missing",
                        topic=TF_TOPIC,
                        message=(
                            f"{source} -> {target} was never resolvable: "
                            f"frame(s) {', '.join(absent)} never appeared"
                        ),
                        details={"required": [source, target], "missing_frames": absent},
                    )
                )
                continue

            missing = self._unavailable(ctx, source, target)
            if not missing:
                continue

            intervals = [
                {"start": round(a - origin, 6), "end": round(b - origin, 6),
                 "duration_s": round(b - a, 6)}
                for a, b in missing
            ]
            worst = max(intervals, key=lambda i: i["duration_s"])
            total = sum(i["duration_s"] for i in intervals)

            findings.append(
                Finding(
                    level=Level.FAIL,
                    code="tf_unavailable",
                    topic=TF_TOPIC,
                    clock=Clock.HEADER,
                    message=(
                        f"{source} -> {target} unavailable for {total:.2f} s across "
                        f"{len(intervals)} interval(s) "
                        f"(worst {worst['duration_s']:.2f} s at {worst['start']:.2f} s)"
                    ),
                    t_start=intervals[0]["start"],
                    t_end=intervals[-1]["end"],
                    details={
                        "required": [source, target],
                        "count": len(intervals),
                        "total_s": round(total, 6),
                        "intervals": intervals,
                    },
                )
            )
        return findings
