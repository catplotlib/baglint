"""The YAML contract a bag is validated against.

Topic keys may be glob patterns (``/camera/*``); the first matching entry wins,
so list specific topics before wildcards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import yaml


class SpecError(ValueError):
    pass


_TOPIC_KEYS = {"min_rate", "max_gap_ms", "required"}


@dataclass(frozen=True)
class TopicSpec:
    pattern: str
    min_rate: float | None = None
    max_gap_ms: float | None = None
    required: bool = True


@dataclass(frozen=True)
class Spec:
    topics: list[TopicSpec] = field(default_factory=list)
    required_transforms: list[tuple[str, str]] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "Spec":
        return cls()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Spec":
        with Path(path).open() as f:
            return cls.from_dict(yaml.safe_load(f) or {})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Spec":
        if not isinstance(data, dict):
            raise SpecError("spec must be a mapping at the top level")

        topics = []
        for pattern, cfg in (data.get("topics") or {}).items():
            cfg = cfg or {}
            if not isinstance(cfg, dict):
                raise SpecError(f"topic '{pattern}': expected a mapping, got {type(cfg).__name__}")
            unknown = set(cfg) - _TOPIC_KEYS
            if unknown:
                raise SpecError(
                    f"topic '{pattern}': unknown key(s) {sorted(unknown)}; "
                    f"valid keys are {sorted(_TOPIC_KEYS)}"
                )
            topics.append(
                TopicSpec(
                    pattern=pattern,
                    min_rate=cfg.get("min_rate"),
                    max_gap_ms=cfg.get("max_gap_ms"),
                    required=cfg.get("required", True),
                )
            )

        transforms = []
        for pair in ((data.get("transforms") or {}).get("required") or []):
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise SpecError(f"transforms.required entries must be [parent, child] pairs, got {pair!r}")
            transforms.append((str(pair[0]), str(pair[1])))

        return cls(topics=topics, required_transforms=transforms)

    def for_topic(self, topic: str) -> TopicSpec | None:
        for ts in self.topics:
            if ts.pattern == topic or fnmatchcase(topic, ts.pattern):
                return ts
        return None

    def literal_topics(self) -> list[TopicSpec]:
        """Spec entries naming a concrete topic, i.e. those we can require to exist."""
        return [t for t in self.topics if not any(c in t.pattern for c in "*?[")]
