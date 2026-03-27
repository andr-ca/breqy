"""Tests for breqy.tui.widgets.stream_buffer — StreamBuffer."""
from __future__ import annotations

import pytest

from breqy.tui.widgets.stream_buffer import StreamBuffer


class TestStreamBufferInit:
    """Test StreamBuffer initialization."""

    def test_creates_empty_buffer(self) -> None:
        buf = StreamBuffer()
        assert not buf.has_message("msg_nonexistent")


class TestStreamBufferAddChunk:
    """Test chunk accumulation."""

    def test_adds_first_chunk(self) -> None:
        buf = StreamBuffer()
        text = buf.add_chunk("msg_1", "Hello", chunk_index=0)
        assert text == "Hello"

    def test_accumulates_multiple_chunks_in_order(self) -> None:
        buf = StreamBuffer()
        buf.add_chunk("msg_1", "Hello", chunk_index=0)
        buf.add_chunk("msg_1", " world", chunk_index=1)
        text = buf.add_chunk("msg_1", "!", chunk_index=2)
        assert text == "Hello world!"

    def test_handles_out_of_order_chunks(self) -> None:
        buf = StreamBuffer()
        buf.add_chunk("msg_1", " world", chunk_index=1)
        text = buf.add_chunk("msg_1", "Hello", chunk_index=0)
        assert text == "Hello world"

    def test_tracks_separate_messages_independently(self) -> None:
        buf = StreamBuffer()
        buf.add_chunk("msg_1", "First", chunk_index=0)
        buf.add_chunk("msg_2", "Second", chunk_index=0)
        assert buf.get_text("msg_1") == "First"
        assert buf.get_text("msg_2") == "Second"

    def test_has_message_returns_true_after_add(self) -> None:
        buf = StreamBuffer()
        buf.add_chunk("msg_1", "Hello", chunk_index=0)
        assert buf.has_message("msg_1")


class TestStreamBufferComplete:
    """Test message completion."""

    def test_returns_full_text_on_complete(self) -> None:
        buf = StreamBuffer()
        buf.add_chunk("msg_1", "Hello", chunk_index=0)
        buf.add_chunk("msg_1", " world", chunk_index=1)
        result = buf.complete("msg_1")
        assert result == "Hello world"

    def test_removes_buffer_after_complete(self) -> None:
        buf = StreamBuffer()
        buf.add_chunk("msg_1", "Hello", chunk_index=0)
        buf.complete("msg_1")
        assert not buf.has_message("msg_1")

    def test_complete_nonexistent_message_returns_empty(self) -> None:
        buf = StreamBuffer()
        result = buf.complete("msg_nonexistent")
        assert result == ""


class TestStreamBufferGetText:
    """Test get_text method."""

    def test_returns_accumulated_text(self) -> None:
        buf = StreamBuffer()
        buf.add_chunk("msg_1", "Hello", chunk_index=0)
        buf.add_chunk("msg_1", " world", chunk_index=1)
        assert buf.get_text("msg_1") == "Hello world"

    def test_does_not_remove_buffer(self) -> None:
        buf = StreamBuffer()
        buf.add_chunk("msg_1", "Hello", chunk_index=0)
        buf.get_text("msg_1")
        assert buf.has_message("msg_1")

    def test_returns_empty_for_nonexistent_message(self) -> None:
        buf = StreamBuffer()
        assert buf.get_text("msg_nonexistent") == ""
