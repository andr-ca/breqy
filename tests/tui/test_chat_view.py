"""Tests for breqy.tui.widgets.chat_view — ChatView widget."""

from __future__ import annotations

import pytest

from textual.app import App, ComposeResult
from textual.widgets import RichLog

from breqy.domain.enums import MessageRole
from breqy.tui.widgets.chat_view import ChatView


class ChatViewApp(App[None]):
    """Minimal app that mounts a ChatView for testing."""

    def compose(self) -> ComposeResult:
        yield ChatView()


class TestChatViewCompose:
    """Test that ChatView mounts a RichLog."""

    @pytest.mark.asyncio
    async def test_mounts_rich_log_widget(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            logs = app.query(RichLog)
            assert len(logs) == 1

    @pytest.mark.asyncio
    async def test_log_widget_property(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            log = chat.log_widget
            assert isinstance(log, RichLog)


class TestChatViewRolePrefix:
    """Test _role_prefix static method returns correct prefixes."""

    def test_user_prefix(self) -> None:
        prefix = ChatView._role_prefix(MessageRole.USER)
        assert "You:" in prefix

    def test_assistant_prefix_default(self) -> None:
        prefix = ChatView._role_prefix(MessageRole.ASSISTANT)
        assert "Assistant:" in prefix

    def test_assistant_prefix_with_agent_id(self) -> None:
        prefix = ChatView._role_prefix(MessageRole.ASSISTANT, agent_id="Breqy")
        assert "Breqy:" in prefix
        assert "Assistant" not in prefix

    def test_system_prefix(self) -> None:
        prefix = ChatView._role_prefix(MessageRole.SYSTEM)
        assert "System:" in prefix

    def test_tool_prefix(self) -> None:
        prefix = ChatView._role_prefix(MessageRole.TOOL)
        assert "Tool:" in prefix


class TestChatViewAddMessage:
    """Test add_message renders with correct prefix."""

    @pytest.mark.asyncio
    async def test_add_user_message(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.add_message(MessageRole.USER, "Hello!")
            await pilot.pause()
            # RichLog stores lines internally; verify the write was called
            # by checking the line count
            log = chat.log_widget
            assert len(log.lines) == 1

    @pytest.mark.asyncio
    async def test_add_assistant_message(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.add_message(MessageRole.ASSISTANT, "I can help!", agent_id="Breqy")
            await pilot.pause()
            assert len(chat.log_widget.lines) == 1

    @pytest.mark.asyncio
    async def test_add_system_message(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.add_message(MessageRole.SYSTEM, "Session started")
            await pilot.pause()
            assert len(chat.log_widget.lines) == 1

    @pytest.mark.asyncio
    async def test_add_tool_message(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.add_message(MessageRole.TOOL, "Command output here")
            await pilot.pause()
            assert len(chat.log_widget.lines) == 1

    @pytest.mark.asyncio
    async def test_add_multiple_messages(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.add_message(MessageRole.USER, "Hello!")
            chat.add_message(MessageRole.ASSISTANT, "Hi there!")
            chat.add_message(MessageRole.SYSTEM, "Session started")
            await pilot.pause()
            assert len(chat.log_widget.lines) == 3


class TestChatViewStreaming:
    """Test streaming chunk support."""

    @pytest.mark.asyncio
    async def test_add_chunk_accumulates_in_buffer(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.add_chunk("msg_1", "Hello", chunk_index=0)
            chat.add_chunk("msg_1", " world", chunk_index=1)
            assert chat._stream_buffer.get_text("msg_1") == "Hello world"

    @pytest.mark.asyncio
    async def test_complete_stream_writes_final_text(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.add_chunk("msg_1", "Hello", chunk_index=0)
            chat.add_chunk("msg_1", " world", chunk_index=1)
            chat.complete_stream("msg_1", role=MessageRole.ASSISTANT)
            await pilot.pause()
            assert len(chat.log_widget.lines) == 1

    @pytest.mark.asyncio
    async def test_complete_stream_clears_buffer(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.add_chunk("msg_1", "Hello", chunk_index=0)
            chat.complete_stream("msg_1", role=MessageRole.ASSISTANT)
            assert not chat._stream_buffer.has_message("msg_1")

    @pytest.mark.asyncio
    async def test_complete_stream_nonexistent_message_noop(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            # Should not raise
            chat.complete_stream("msg_nonexistent", role=MessageRole.ASSISTANT)
            await pilot.pause()
            assert len(chat.log_widget.lines) == 0


class TestChatViewClear:
    """Test clear_messages empties the log."""

    @pytest.mark.asyncio
    async def test_clear_messages(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.add_message(MessageRole.USER, "Hello!")
            chat.add_message(MessageRole.ASSISTANT, "Hi!")
            await pilot.pause()
            assert len(chat.log_widget.lines) == 2
            chat.clear_messages()
            await pilot.pause()
            assert len(chat.log_widget.lines) == 0


class TestThinkingIndicator:
    """ChatView.show_thinking_indicator / hide_thinking_indicator."""

    @pytest.mark.asyncio
    async def test_show_thinking_indicator_mounts_widget(self) -> None:
        from textual.widgets import Static

        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.show_thinking_indicator()
            await pilot.pause()
            indicators = app.query("#thinking-indicator")
            assert len(indicators) == 1

    @pytest.mark.asyncio
    async def test_show_thinking_indicator_is_idempotent(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.show_thinking_indicator()
            chat.show_thinking_indicator()
            await pilot.pause()
            indicators = app.query("#thinking-indicator")
            assert len(indicators) == 1

    @pytest.mark.asyncio
    async def test_hide_thinking_indicator_removes_widget(self) -> None:
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.show_thinking_indicator()
            await pilot.pause()
            chat.hide_thinking_indicator()
            await pilot.pause()
            indicators = app.query("#thinking-indicator")
            assert len(indicators) == 0

    @pytest.mark.asyncio
    async def test_hide_thinking_indicator_is_noop_when_none_shown(self) -> None:
        """hide_thinking_indicator does not raise if no indicator is mounted."""
        app = ChatViewApp()
        async with app.run_test() as pilot:
            chat = app.query_one(ChatView)
            chat.hide_thinking_indicator()  # should not raise
            await pilot.pause()
            indicators = app.query("#thinking-indicator")
            assert len(indicators) == 0
