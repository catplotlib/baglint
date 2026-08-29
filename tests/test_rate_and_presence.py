import pytest

from baglint import Spec, run
from baglint.findings import Level
from fixtures import SynthBag


def test_rate_below_minimum_fails(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/camera/image", rate=12.0)
    spec = Spec.from_dict({"topics": {"/camera/image": {"min_rate": 25}}})

    finding = next(f for f in run(bag.write(), spec).findings if f.code == "rate_below_min")
    assert finding.level is Level.FAIL
    assert finding.details["rate_hz"] == pytest.approx(12.0, abs=0.1)


def test_rate_at_or_above_minimum_passes(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/camera/image", rate=30.0)
    spec = Spec.from_dict({"topics": {"/camera/image": {"min_rate": 25}}})
    assert run(bag.write(), spec).findings == []


def test_rate_measured_over_topic_span_not_bag_span(tmp_path):
    """A 30 Hz topic present for only half the bag is still 30 Hz."""
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/camera/image", rate=30.0).clip(end=5.0)
    bag.topic("/other", rate=10)
    spec = Spec.from_dict({"topics": {"/camera/image": {"min_rate": 25}}})
    assert run(bag.write(), spec).findings == []


def test_missing_required_topic_fails(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=100)
    spec = Spec.from_dict({"topics": {"/imu": {"min_rate": 100}}})

    finding = next(f for f in run(bag.write(), spec).findings if f.code == "missing_topic")
    assert finding.topic == "/imu"


def test_glob_pattern_matching_nothing_is_not_an_error(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=100)
    spec = Spec.from_dict({"topics": {"/camera/*": {"min_rate": 25}}})
    assert run(bag.write(), spec).findings == []


def test_glob_pattern_applies_to_matching_topics(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/camera/left", rate=10.0)
    spec = Spec.from_dict({"topics": {"/camera/*": {"min_rate": 25}}})

    finding = next(f for f in run(bag.write(), spec).findings if f.code == "rate_below_min")
    assert finding.topic == "/camera/left"
