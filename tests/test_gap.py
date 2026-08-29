import pytest

from baglint import Spec, run
from baglint.findings import Clock, Level
from fixtures import SynthBag

SPEC = Spec.from_dict({"topics": {"/joint_states": {"max_gap_ms": 10}}})


def build(tmp_path, mutate=None, rate=500.0):
    bag = SynthBag(tmp_path / "bag.mcap")
    topic = bag.topic("/joint_states", rate=rate)
    if mutate:
        mutate(topic)
    return bag.write()


def test_clean_bag_produces_no_findings(tmp_path):
    report = run(build(tmp_path), SPEC)
    assert report.findings == []
    assert report.exit_code() == 0


def test_injected_gap_is_found_at_the_right_time(tmp_path):
    path = build(tmp_path, lambda t: t.gap(at=4.0, ms=50))
    report = run(path, SPEC)

    gaps = [f for f in report.findings if f.code == "gap"]
    assert len(gaps) == 1

    finding = gaps[0]
    assert finding.level is Level.FAIL
    assert finding.topic == "/joint_states"
    assert finding.clock is Clock.LOG
    assert finding.details["count"] == 1
    # 25 samples dropped at 500 Hz, so the surviving neighbours sit ~52 ms apart.
    assert finding.details["worst_ms"] == pytest.approx(52.0, abs=0.5)
    assert finding.t_start == pytest.approx(3.998, abs=0.002)


def test_multiple_gaps_are_counted(tmp_path):
    path = build(tmp_path, lambda t: t.gap(at=2.0, ms=50).gap(at=6.0, ms=80))
    report = run(path, SPEC)

    finding = next(f for f in report.findings if f.code == "gap")
    assert finding.details["count"] == 2
    assert finding.details["worst_ms"] == pytest.approx(82.0, abs=0.5)


def test_gap_under_threshold_is_ignored(tmp_path):
    # 4 ms of dropped messages, under the spec's 10 ms tolerance.
    path = build(tmp_path, lambda t: t.gap(at=4.0, ms=4))
    assert run(path, SPEC).findings == []


def test_late_starting_topic_reports_no_boundary_gap(tmp_path):
    """A topic that starts late and ends early must not be blamed for the
    silence before its first and after its last message."""
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=500).clip(start=3.0, end=6.0)
    bag.topic("/other", rate=10)  # spans the full bag, so the bag is 10 s long
    report = run(bag.write(), SPEC)

    assert [f for f in report.findings if f.code == "gap"] == []


def test_topic_without_spec_is_not_gap_checked(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/unspecified", rate=500).gap(at=4.0, ms=500)
    bag.topic("/joint_states", rate=500)  # keeps PresenceCheck quiet

    report = run(bag.write(), SPEC)
    assert [f for f in report.findings if f.code == "gap"] == []
