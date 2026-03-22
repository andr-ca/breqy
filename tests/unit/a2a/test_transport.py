"""Tests for A2A transport framing."""
from __future__ import annotations

import asyncio
import struct

import pytest

from breqy.a2a.envelope import Envelope
from breqy.a2a.transport import FrameReader, FrameWriter
from breqy.domain.events import MessageSentEvent


def _make_frame(payload_bytes: bytes) -> bytes:
    """Build a length-prefixed frame manually."""
    return struct.pack("!I", len(payload_bytes)) + payload_bytes


@pytest.mark.asyncio
async def test_frame_reader_reads_single_frame():
    """FrameReader.read_frame() reads one length-prefixed frame."""
    payload = b'{"hello": "world"}'
    raw = _make_frame(payload)
    reader = asyncio.StreamReader()
    reader.feed_data(raw)
    reader.feed_eof()
    frame_reader = FrameReader(reader)
    result = await frame_reader.read_frame()
    assert result == payload


@pytest.mark.asyncio
async def test_frame_reader_reads_envelope():
    """FrameReader.read_envelope() returns a parsed Envelope."""
    event = MessageSentEvent(
        session_id="ses_tr",
        message_id="msg_tr1",
        role="user",
        content="transport test",
    )
    env = Envelope.from_event(event)
    payload = env.model_dump_json().encode()
    raw = _make_frame(payload)

    reader = asyncio.StreamReader()
    reader.feed_data(raw)
    reader.feed_eof()

    frame_reader = FrameReader(reader)
    result = await frame_reader.read_envelope()
    assert result is not None
    assert result.session_id == "ses_tr"
    assert result.payload["content"] == "transport test"


@pytest.mark.asyncio
async def test_frame_reader_returns_none_on_eof():
    """FrameReader.read_frame() returns None when reader hits EOF immediately."""
    reader = asyncio.StreamReader()
    reader.feed_eof()
    frame_reader = FrameReader(reader)
    result = await frame_reader.read_frame()
    assert result is None
