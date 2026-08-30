import json

import yaml

from baglint.cli import main
from fixtures import SynthBag


def write_spec(tmp_path, data):
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_clean_bag_exits_zero(tmp_path, capsys):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=500)
    spec = write_spec(tmp_path, {"topics": {"/joint_states": {"max_gap_ms": 10}}})

    assert main([str(bag.write()), "--spec", str(spec)]) == 0
    assert "no findings" in capsys.readouterr().out


def test_failing_bag_exits_one(tmp_path, capsys):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=500).gap(at=4.0, ms=50)
    spec = write_spec(tmp_path, {"topics": {"/joint_states": {"max_gap_ms": 10}}})

    assert main([str(bag.write()), "--spec", str(spec)]) == 1
    out = capsys.readouterr().out
    assert "FAIL /joint_states" in out
    assert "[log_time]" in out


def test_json_output_is_machine_readable(tmp_path, capsys):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=500).gap(at=4.0, ms=50)
    spec = write_spec(tmp_path, {"topics": {"/joint_states": {"max_gap_ms": 10}}})

    main([str(bag.write()), "--spec", str(spec), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["FAIL"] == 1
    assert payload["findings"][0]["code"] == "gap"
    assert payload["findings"][0]["clock"] == "log_time"


def test_missing_file_exits_two(tmp_path, capsys):
    assert main([str(tmp_path / "nope.mcap")]) == 2


def test_bad_spec_exits_two(tmp_path, capsys):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=10)
    spec = write_spec(tmp_path, {"topics": {"/joint_states": {"nonsense": 1}}})

    assert main([str(bag.write()), "--spec", str(spec)]) == 2
    assert "bad spec" in capsys.readouterr().err


def test_no_spec_reports_that_nothing_was_validated(tmp_path, capsys):
    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=500)

    assert main([str(bag.write())]) == 0
    assert "nothing was validated" in capsys.readouterr().out


def test_init_prints_a_usable_spec(tmp_path, capsys):
    import yaml as _yaml

    bag = SynthBag(tmp_path / "bag.mcap")
    bag.topic("/joint_states", rate=500)

    assert main([str(bag.write()), "--init"]) == 0
    parsed = _yaml.safe_load(capsys.readouterr().out)
    assert "/joint_states" in parsed["topics"]
