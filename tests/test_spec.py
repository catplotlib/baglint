import pytest

from baglint.spec import Spec, SpecError


def test_unknown_topic_key_is_rejected():
    with pytest.raises(SpecError, match="unknown key"):
        Spec.from_dict({"topics": {"/imu": {"min_rat": 100}}})


def test_first_matching_pattern_wins():
    spec = Spec.from_dict(
        {"topics": {"/camera/left": {"min_rate": 30}, "/camera/*": {"min_rate": 10}}}
    )
    assert spec.for_topic("/camera/left").min_rate == 30
    assert spec.for_topic("/camera/right").min_rate == 10


def test_transforms_are_parsed_as_pairs():
    spec = Spec.from_dict({"transforms": {"required": [["camera_link", "base_link"]]}})
    assert spec.required_transforms == [("camera_link", "base_link")]


def test_malformed_transform_pair_is_rejected():
    with pytest.raises(SpecError, match="parent, child"):
        Spec.from_dict({"transforms": {"required": ["camera_link"]}})


def test_empty_spec_matches_nothing():
    assert Spec.empty().for_topic("/anything") is None
