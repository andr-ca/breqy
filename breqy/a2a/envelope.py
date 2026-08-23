"""A2A Envelope: the wire format for all engine-agent communication.

Every message on the wire is a length-prefixed JSON envelope containing:
- event metadata (type, version, IDs, timestamp)
- payload (event-specific fields)

Wire encoding: 4-byte big-endian uint32 length prefix + UTF-8 JSON bytes.
"""
from __future__ import annotations

import struct
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel, Field

from breqy.domain.enums import EventType
from breqy.domain.events import Event, deserialize_event
from breqy.domain.ids import generate_prefixed_id

logger = structlog.get_logger(__name__)


class Envelope(BaseModel):
    """Wire-format envelope wrapping a typed event."""

    event_id: str = Field(default_factory=lambda: generate_prefixed_id("evt"))
    event_type: EventType
    schema_version: int = 1
    session_id: str
    agent_id: str = ""
    correlation_id: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_event(cls, event: Event) -> Envelope:
        """Create an envelope from a typed Event."""
        data = event.model_dump()
        envelope_keys = {
            "event_id",
            "event_type",
            "schema_version",
            "session_id",
            "agent_id",
            "correlation_id",
            "timestamp",
        }
        payload = {k: v for k, v in data.items() if k not in envelope_keys}
        return cls(
            event_id=event.event_id,
            event_type=event.event_type,
            schema_version=event.schema_version,
            session_id=event.session_id,
            agent_id=event.agent_id,
            correlation_id=event.correlation_id,
            timestamp=(
                event.timestamp.isoformat()
                if isinstance(event.timestamp, datetime)
                else str(event.timestamp)
            ),
            payload=payload,
        )

    def to_event(self) -> Event:
        """Reconstruct the typed Event from this envelope."""
        data = {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            **self.payload,
        }
        try:
            return deserialize_event(data)
        except Exception:
            logger.warning(
                "Envelope deserialization failed",
                event_type=self.event_type.value,
                event_id=self.event_id,
            )
            raise


def encode_envelope(envelope: Envelope) -> bytes:
    """Encode an envelope to length-prefixed JSON bytes."""
    json_bytes = envelope.model_dump_json().encode("utf-8")
    length = struct.pack("!I", len(json_bytes))
    return length + json_bytes


def decode_envelope(data: bytes) -> Envelope:
    """Decode an envelope from length-prefixed JSON bytes."""
    if len(data) < 4:
        raise ValueError("Data too short for length prefix")
    length = struct.unpack("!I", data[:4])[0]
    json_bytes = data[4 : 4 + length]
    return Envelope.model_validate_json(json_bytes)
