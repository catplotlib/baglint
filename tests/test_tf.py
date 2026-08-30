import pytest

from baglint import Spec, run
from baglint.findings import Clock, Level
from fixtures import SynthBag

SPEC = Spec.from_dict(
    {"transforms": {"required": [["camera_link", "base_link"]], "max_stale_ms": 500}}
)


def test_continuous_chain_is_available(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap", duration=20.0)
    bag.topic("/joint_states", rate=100)
    bag.transform("base_link", "torso", rate=50)
    bag.transform("torso", "camera_link", rate=50)

    assert run(bag.write(), SPEC).findings == []


def test_broken_link_reports_the_window(tmp_path):
    """torso -> camera_link stops publishing between 8 s and 13 s. The chain
    stays usable for max_stale_ms past the last update, so the reported window
    opens at 8 s plus that tolerance."""
    bag = SynthBag(tmp_path / "bag.mcap", duration=20.0)
    bag.topic("/joint_states", rate=100)
    bag.transform("base_link", "torso", rate=50)
    bag.transform("torso", "camera_link", rate=50, end=8.0)
    bag.transform("torso", "camera_link", rate=50, start=13.0)

    finding = next(f for f in run(bag.write(), SPEC).findings if f.code == "tf_unavailable")
    assert finding.level is Level.FAIL
    assert finding.clock is Clock.HEADER
    assert finding.details["count"] == 1

    interval = finding.details["intervals"][0]
    assert interval["start"] == pytest.approx(8.48, abs=0.1)   # 7.98 + 500 ms
    assert interval["end"] == pytest.approx(13.0, abs=0.1)


def test_static_transform_counts_for_the_whole_recording(tmp_path):
    """/tf_static is latched: published once, valid throughout."""
    bag = SynthBag(tmp_path / "bag.mcap", duration=20.0)
    bag.topic("/joint_states", rate=100)
    bag.transform("base_link", "torso", rate=50)
    bag.transform("torso", "camera_link", static=True)

    assert run(bag.write(), SPEC).findings == []


def test_multi_hop_path_is_traversed(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap", duration=10.0)
    bag.topic("/joint_states", rate=100)
    bag.transform("base_link", "torso", rate=50)
    bag.transform("torso", "head", rate=50)
    bag.transform("head", "camera_mount", rate=50)
    bag.transform("camera_mount", "camera_link", rate=50)

    assert run(bag.write(), SPEC).findings == []


def test_disconnected_tree_is_unavailable_throughout(tmp_path):
    """Both frames exist but nothing joins the two halves."""
    bag = SynthBag(tmp_path / "bag.mcap", duration=10.0)
    bag.topic("/joint_states", rate=100)
    bag.transform("base_link", "torso", rate=50)
    bag.transform("odom", "camera_link", rate=50)

    finding = next(f for f in run(bag.write(), SPEC).findings if f.code == "tf_unavailable")
    assert finding.details["total_s"] == pytest.approx(10.0, abs=0.2)


def test_unknown_frame_is_reported_distinctly(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap", duration=10.0)
    bag.topic("/joint_states", rate=100)
    bag.transform("base_link", "torso", rate=50)

    finding = next(f for f in run(bag.write(), SPEC).findings if f.code == "tf_frame_missing")
    assert finding.details["missing_frames"] == ["camera_link"]


def test_direction_does_not_matter(tmp_path):
    """A transform can be inverted, so base_link -> camera_link resolves from
    edges published the other way round."""
    bag = SynthBag(tmp_path / "bag.mcap", duration=10.0)
    bag.topic("/joint_states", rate=100)
    bag.transform("base_link", "torso", rate=50)
    bag.transform("torso", "camera_link", rate=50)

    spec = Spec.from_dict({"transforms": {"required": [["base_link", "camera_link"]]}})
    assert run(bag.write(), spec).findings == []


def test_slow_publisher_within_staleness_is_fine(tmp_path):
    """A 4 Hz transform has 250 ms between updates, inside the 500 ms default."""
    bag = SynthBag(tmp_path / "bag.mcap", duration=10.0)
    bag.topic("/joint_states", rate=100)
    bag.transform("base_link", "torso", rate=50)
    bag.transform("torso", "camera_link", rate=4)

    assert run(bag.write(), SPEC).findings == []


def test_staleness_threshold_is_configurable(tmp_path):
    """The same 4 Hz transform fails once the tolerance drops below its period."""
    bag = SynthBag(tmp_path / "bag.mcap", duration=10.0)
    bag.topic("/joint_states", rate=100)
    bag.transform("base_link", "torso", rate=50)
    bag.transform("torso", "camera_link", rate=4)

    strict = Spec.from_dict(
        {"transforms": {"required": [["camera_link", "base_link"]], "max_stale_ms": 100}}
    )
    assert any(f.code == "tf_unavailable" for f in run(bag.write(), strict).findings)


def test_tf_is_not_read_without_required_transforms(tmp_path):
    bag = SynthBag(tmp_path / "bag.mcap", duration=10.0)
    bag.topic("/joint_states", rate=100)
    bag.transform("base_link", "torso", rate=50)

    assert run(bag.write(), Spec.empty()).findings == []
