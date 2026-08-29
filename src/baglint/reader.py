"""Bag access, one storage backend at a time.

Only MCAP is implemented. The BagReader protocol exists so a sqlite3 (.db3)
backend can be added without any check knowing the difference.

Payloads are deserialized lazily: checks declare the topics they need decoded
and everything else is walked as raw bytes. On a multi-GB bag that is the
difference between seconds and minutes, since gap and rate analysis need only
log_time, which is in the message record itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Protocol

from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory


@dataclass(frozen=True)
class ChannelInfo:
    topic: str
    schema_name: str | None
    message_encoding: str


@dataclass(frozen=True)
class Message:
    topic: str
    log_time_ns: int
    publish_time_ns: int
    decoded: Any | None = None


class BagReader(Protocol):
    def channels(self) -> list[ChannelInfo]: ...

    def iter_messages(self, decode: Iterable[str] = ()) -> Iterator[Message]: ...

    @property
    def start_ns(self) -> int: ...

    @property
    def end_ns(self) -> int: ...

    @property
    def message_count(self) -> int: ...


class McapBagReader:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._file = None
        self._reader = None
        self._decoders: dict[int, Any] = {}
        self._factory = DecoderFactory()

    def __enter__(self) -> "McapBagReader":
        self._file = self.path.open("rb")
        self._reader = make_reader(self._file)
        self._summary = self._reader.get_summary()
        return self

    def __exit__(self, *exc) -> None:
        if self._file is not None:
            self._file.close()

    def channels(self) -> list[ChannelInfo]:
        if self._summary is None:
            return self._scan_channels()
        return [
            ChannelInfo(c.topic, self._schema_name(c.schema_id), c.message_encoding)
            for c in self._summary.channels.values()
        ]

    def _schema_name(self, schema_id: int) -> str | None:
        if self._summary is None:
            return None
        schema = self._summary.schemas.get(schema_id)
        return schema.name if schema else None

    def _scan_channels(self) -> list[ChannelInfo]:
        """Fallback for unindexed bags, which carry no summary section."""
        seen: dict[str, ChannelInfo] = {}
        for schema, channel, _ in self._reader.iter_messages():
            if channel.topic not in seen:
                seen[channel.topic] = ChannelInfo(
                    channel.topic,
                    schema.name if schema else None,
                    channel.message_encoding,
                )
        return list(seen.values())

    def iter_messages(self, decode: Iterable[str] = ()) -> Iterator[Message]:
        wanted = frozenset(decode)
        for schema, channel, message in self._reader.iter_messages():
            decoded = None
            if channel.topic in wanted:
                decoder = self._decoder_for(channel.id, channel.message_encoding, schema)
                if decoder is not None:
                    decoded = decoder(message.data)
            yield Message(
                topic=channel.topic,
                log_time_ns=message.log_time,
                publish_time_ns=message.publish_time,
                decoded=decoded,
            )

    def _decoder_for(self, channel_id: int, encoding: str, schema) -> Any:
        if channel_id not in self._decoders:
            self._decoders[channel_id] = self._factory.decoder_for(encoding, schema)
        return self._decoders[channel_id]

    @property
    def start_ns(self) -> int:
        stats = self._summary.statistics if self._summary else None
        return stats.message_start_time if stats else 0

    @property
    def end_ns(self) -> int:
        stats = self._summary.statistics if self._summary else None
        return stats.message_end_time if stats else 0

    @property
    def message_count(self) -> int:
        stats = self._summary.statistics if self._summary else None
        return stats.message_count if stats else 0
