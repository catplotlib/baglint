import yaml

from baglint import Spec, run
from baglint.init import generate_spec
from fixtures import SynthBag


def test_generated_spec_validates_its_own_recording(tmp_path):
    """The round trip has to hold: a spec generated from a recording must not
    then flag that recording. If it does, the generated bounds are too tight."""
    bag = SynthBag(tmp_path / "good.mcap")
    bag.topic("/joint_states", rate=500)
    bag.topic("/camera/image", rate=30)
    bag.topic("/imu", rate=100)
    path = bag.write()

    spec_text = generate_spec(path)
    spec = Spec.from_dict(yaml.safe_load(spec_text))

    assert run(path, spec).findings == []


def test_generated_spec_covers_every_topic(tmp_path):
    bag = SynthBag(tmp_path / "good.mcap")
    bag.topic("/joint_states", rate=500)
    bag.topic("/imu", rate=100)

    parsed = yaml.safe_load(generate_spec(bag.write()))
    assert sorted(parsed["topics"]) == ["/imu", "/joint_states"]


def test_bounds_sit_outside_observed_values(tmp_path):
    bag = SynthBag(tmp_path / "good.mcap")
    bag.topic("/imu", rate=100)

    parsed = yaml.safe_load(generate_spec(bag.write()))
    entry = parsed["topics"]["/imu"]

    assert entry["min_rate"] < 100          # below observed rate
    assert entry["max_gap_ms"] > 10         # above the 10 ms nominal period


def test_margin_widens_the_rate_bound(tmp_path):
    bag = SynthBag(tmp_path / "good.mcap")
    bag.topic("/imu", rate=100)
    path = bag.write()

    tight = yaml.safe_load(generate_spec(path, margin=0.05))["topics"]["/imu"]["min_rate"]
    loose = yaml.safe_load(generate_spec(path, margin=0.50))["topics"]["/imu"]["min_rate"]
    assert loose < tight


def test_sparse_topic_is_presence_only(tmp_path):
    """A latched topic has no meaningful rate, so no rate bound is generated."""
    bag = SynthBag(tmp_path / "good.mcap")
    bag.topic("/imu", rate=100)
    bag.topic("/tf_static", rate=0.1)  # one message over the 10 s bag

    parsed = yaml.safe_load(generate_spec(bag.write()))
    assert parsed["topics"]["/tf_static"] is None      # comment only, no keys
    assert parsed["topics"]["/imu"]["min_rate"] > 0


def test_a_recording_with_defects_generates_slack_bounds(tmp_path):
    """Generating from a bad recording bakes its defects into the spec. The
    round trip still holds, which is why --init must be pointed at a good run."""
    bag = SynthBag(tmp_path / "bad.mcap")
    bag.topic("/joint_states", rate=500).gap(at=4.0, ms=120)
    path = bag.write()

    parsed = yaml.safe_load(generate_spec(path))
    assert parsed["topics"]["/joint_states"]["max_gap_ms"] > 120
    assert run(path, Spec.from_dict(parsed)).findings == []


def test_empty_recording_generates_an_empty_spec(tmp_path):
    from mcap_ros2.writer import Writer

    path = tmp_path / "empty.mcap"
    with path.open("wb") as f:
        Writer(f).finish()

    assert yaml.safe_load(generate_spec(path))["topics"] == {}
