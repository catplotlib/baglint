import pytest
from mcap_ros2.writer import Writer

from baglint import Spec, run
from baglint.findings import Clock, Finding, Level
from fixtures import SynthBag


def test_empty_bag_does_not_crash(tmp_path):
    path = tmp_path / "empty.mcap"
    with path.open("wb") as f:
        Writer(f).finish()

    report = run(path, Spec.from_dict({"topics": {"/imu": {"min_rate": 100}}}))
    assert report.topic_count == 0
    assert report.duration_s == 0.0
    assert [f.code for f in report.findings] == ["missing_topic"]


def test_single_message_topic_reports_unmeasurable_rate(tmp_path):
    """One message has no interval to measure, so the rate is unknown rather
    than zero -- reporting 0 Hz would be a fabricated number."""
    bag = SynthBag(tmp_path / "bag.mcap", duration=1.0)
    bag.topic("/imu", rate=1.0)  # exactly one sample
    spec = Spec.from_dict({"topics": {"/imu": {"min_rate": 100}}})

    finding = next(f for f in run(bag.write(), spec).findings if f.code == "rate_unmeasurable")
    assert finding.details["count"] == 1


def test_findings_are_hashable_and_dedupe(tmp_path):
    a = Finding(level=Level.FAIL, code="gap", message="m", topic="/t", clock=Clock.LOG,
                details={"count": 1})
    b = Finding(level=Level.FAIL, code="gap", message="m", topic="/t", clock=Clock.LOG,
                details={"count": 99})
    assert len({a, b}) == 1  # details do not affect identity


def test_corrupt_file_exits_two(tmp_path, capsys):
    from baglint.cli import main

    bad = tmp_path / "garbage.mcap"
    bad.write_bytes(b"this is not an mcap file at all")

    assert main([str(bad)]) == 2
    assert "failed to read" in capsys.readouterr().err


def test_strict_promotes_warnings(tmp_path):
    from baglint.report import Report

    warn = Finding(level=Level.WARN, code="x", message="m")
    report = Report(path=tmp_path, findings=[warn], topic_count=1, message_count=1, duration_s=1.0)
    assert report.exit_code() == 0
    assert report.exit_code(strict=True) == 1


def test_version_matches_installed_metadata():
    """The build reads its version from __init__, so these cannot disagree.
    They did once: 0.2.0 shipped reporting 0.1.0."""
    from importlib.metadata import version

    import baglint

    assert baglint.__version__ == version("baglint")
