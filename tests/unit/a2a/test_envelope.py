"""Tests for A2A Envelope format."""
from __future__ import annotations

from breqy.a2a.envelope import Envelope, decode_envelope, encode_envelope
from breqy.domain.enums import EventType
from breqy.domain.events import MessageSentEvent


def test_envelope_from_event():
    """Envelope.from_event extracts metadata and payload correctly."""
    event = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_001",
        role="user",
        content="hello",
    )
    env = Envelope.from_event(event)
    assert env.session_id == "ses_test"
    assert env.event_type == EventType.MESSAGE_SENT
    assert env.payload["content"] == "hello"
    assert env.payload["message_id"] == "msg_001"


def test_envelope_to_event_round_trip():
    """Envelope.to_event reconstructs the original typed event."""
    event = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_002",
        role="user",
        content="round trip",
    )
    env = Envelope.from_event(event)
    restored = env.to_event()
    assert isinstance(restored, MessageSentEvent)
    assert restored.content == "round trip"
    assert restored.session_id == "ses_test"


def test_envelope_json_serialization():
    """Envelope serializes to and from JSON without loss."""
    event = MessageSentEvent(
        session_id="ses_abc",
        message_id="msg_003",
        role="assistant",
        content="json test",
    )
    env = Envelope.from_event(event)
    json_str = env.model_dump_json()
    restored = Envelope.model_validate_json(json_str)
    assert restored.session_id == env.session_id
    assert restored.payload["content"] == "json test"


def test_encode_decode_envelope():
    """encode_envelope and decode_envelope are inverses."""
    event = MessageSentEvent(
        session_id="ses_enc",
        message_id="msg_004",
        role="user",
        content="encode test",
    )
    env = Envelope.from_event(event)
    encoded = encode_envelope(env)
    # first 4 bytes are length prefix
    assert len(encoded) > 4
    decoded = decode_envelope(encoded)
    assert decoded.session_id == env.session_id
    assert decoded.payload["content"] == "encode test"


# ---------------------------------------------------------------------------
# structlog migration
# ---------------------------------------------------------------------------

def test_envelope_uses_structlog():
    """envelope module-level logger is structlog, not stdlib."""
    import logging as _logging
    from breqy.a2a import envelope
    assert hasattr(envelope, "logger")
    assert not isinstance(envelope.logger, _logging.Logger)
