"""Synthetic bag construction with precisely injected defects.

Every check gets tested against a bag whose flaws we chose, so the suite needs
no robot, no recording and no ROS installation -- MCAP embeds its own schemas,
so mcap-ros2-support serializes straight from dicts.

    bag = SynthBag(tmp_path / "b.mcap")
    bag.topic("/joint_states", rate=500).gap(at=4.0, ms=50)
    bag.write()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mcap_ros2.writer import Writer

# A bag that starts at a realistic epoch rather than zero, so anything that
# confuses absolute with bag-relative time fails loudly in tests.
BASE_EPOCH_NS = 1_700_000_000_000_000_000

STAMPED_MSGDEF = """\
std_msgs/Header header
================================================================================
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/Time
int32 sec
uint32 nanosec
"""


@dataclass
class TopicBuilder:
    name: str
    rate: float
    duration: float
    frame_id: str = "test_frame"
    log_times: list[float] = field(default_factory=list)
    stamps: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = int(round(self.duration * self.rate))
        self.log_times = [i / self.rate for i in range(n)]
        self.stamps = list(self.log_times)

    def gap(self, at: float, ms: float) -> "TopicBuilder":
        """Drop every message in [at, at + ms), creating a recording dropout."""
        end = at + ms / 1000.0
        kept = [(t, s) for t, s in zip(self.log_times, self.stamps) if not (at <= t < end)]
        self.log_times = [t for t, _ in kept]
        self.stamps = [s for _, s in kept]
        return self

    def clip(self, start: float | None = None, end: float | None = None) -> "TopicBuilder":
        """Make the topic start late and/or end early relative to the bag."""
        kept = [
            (t, s)
            for t, s in zip(self.log_times, self.stamps)
            if (start is None or t >= start) and (end is None or t <= end)
        ]
        self.log_times = [t for t, _ in kept]
        self.stamps = [s for _, s in kept]
        return self

    def duplicate_stamps(self, count: int, at_index: int = 10) -> "TopicBuilder":
        """Repeat a previous header.stamp on `count` messages, as a broken
        driver would, while log_time keeps advancing normally."""
        for i in range(at_index, min(at_index + count, len(self.stamps))):
            self.stamps[i] = self.stamps[i - 1]
        return self

    def rate_change(self, at: float, new_rate: float) -> "TopicBuilder":
        """Switch to a different publication rate partway through."""
        head = [t for t in self.log_times if t < at]
        n = int(round((self.duration - at) * new_rate))
        tail = [at + i / new_rate for i in range(n)]
        self.log_times = head + tail
        self.stamps = list(self.log_times)
        return self


class SynthBag:
    def __init__(self, path: str | Path, duration: float = 10.0):
        self.path = Path(path)
        self.duration = duration
        self._topics: list[TopicBuilder] = []

    def topic(self, name: str, rate: float, duration: float | None = None) -> TopicBuilder:
        tb = TopicBuilder(name=name, rate=rate, duration=duration or self.duration)
        self._topics.append(tb)
        return tb

    def write(self) -> Path:
        records = []
        for tb in self._topics:
            for log_t, stamp_t in zip(tb.log_times, tb.stamps):
                records.append((BASE_EPOCH_NS + int(round(log_t * 1e9)), tb, stamp_t))
        records.sort(key=lambda r: r[0])

        with self.path.open("wb") as f:
            writer = Writer(f)
            schema = writer.register_msgdef("test_msgs/msg/Stamped", STAMPED_MSGDEF)
            for log_time_ns, tb, stamp_t in records:
                stamp_ns = BASE_EPOCH_NS + int(round(stamp_t * 1e9))
                writer.write_message(
                    topic=tb.name,
                    schema=schema,
                    message={
                        "header": {
                            "stamp": {"sec": stamp_ns // 1_000_000_000, "nanosec": stamp_ns % 1_000_000_000},
                            "frame_id": tb.frame_id,
                        }
                    },
                    log_time=log_time_ns,
                    publish_time=log_time_ns,
                )
            writer.finish()
        return self.path
