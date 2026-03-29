"""Tests for breqy.tui.widgets.message_input — MessageInput widget."""
from __future__ import annotations

import pytest

from textual.app import App, ComposeResult

from breqy.tui.commands import CommandRegistry, CommandResult
from breqy.tui.widgets.message_input import (
    CommandExecuted,
    MessageInput,
    MessageSubmitted,
)


class MessageInputApp(App[None]):
    """Minimal app that mounts a MessageInput for testing."""

    def __init__(self, registry: CommandRegistry | None = None) -> None:
        super().__init__()
        self._cmd_registry = registry

    def compose(self) -> ComposeResult:
        yield MessageInput(command_registry=self._cmd_registry)


class TestMessageInputCompose:
    """Test that MessageInput mounts an Input widget."""

    @pytest.mark.asyncio
    async def test_mounts_inner_input_widget(self) -> None:
        from textual.widgets import Input

        app = MessageInputApp()
        async with app.run_test() as pilot:
            inputs = app.query(Input)
            assert len(inputs) == 1

    @pytest.mark.asyncio
    async def test_inner_input_has_placeholder(self) -> None:
        from textual.widgets import Input

        app = MessageInputApp()
        async with app.run_test() as pilot:
            inp = app.query_one("#message-input", Input)
            assert "message" in inp.placeholder.lower() or "command" in inp.placeholder.lower()


class TestMessageInputRegularSubmit:
    """Test that regular text posts MessageSubmitted."""

    @pytest.mark.asyncio
    async def test_regular_text_posts_message_submitted(self) -> None:
        messages: list[MessageSubmitted] = []

        class CapturingApp(MessageInputApp):
            def on_message_submitted(self, event: MessageSubmitted) -> None:
                messages.append(event)

        app = CapturingApp()
        async with app.run_test() as pilot:
            inp = app.query_one("#message-input")
            inp.value = "Hello world"
            await inp.action_submit()
            await pilot.pause()
            assert len(messages) == 1
            assert messages[0].text == "Hello world"

    @pytest.mark.asyncio
    async def test_input_cleared_after_regular_submit(self) -> None:
        app = MessageInputApp()
        async with app.run_test() as pilot:
            inp = app.query_one("#message-input")
            inp.value = "Hello world"
            await inp.action_submit()
            await pilot.pause()
            assert inp.value == ""


class TestMessageInputEmptySubmit:
    """Test that empty submit does nothing."""

    @pytest.mark.asyncio
    async def test_empty_submit_does_not_post_message(self) -> None:
        messages: list[MessageSubmitted] = []

        class CapturingApp(MessageInputApp):
            def on_message_submitted(self, event: MessageSubmitted) -> None:
                messages.append(event)

        app = CapturingApp()
        async with app.run_test() as pilot:
            inp = app.query_one("#message-input")
            inp.value = ""
            await inp.action_submit()
            await pilot.pause()
            assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_whitespace_only_submit_does_not_post_message(self) -> None:
        messages: list[MessageSubmitted] = []

        class CapturingApp(MessageInputApp):
            def on_message_submitted(self, event: MessageSubmitted) -> None:
                messages.append(event)

        app = CapturingApp()
        async with app.run_test() as pilot:
            inp = app.query_one("#message-input")
            inp.value = "   "
            await inp.action_submit()
            await pilot.pause()
            assert len(messages) == 0


class TestMessageInputSlashCommand:
    """Test slash command dispatch."""

    @pytest.mark.asyncio
    async def test_slash_command_dispatches_to_registry(self) -> None:
        registry = CommandRegistry()
        registry.register(
            "help",
            lambda: CommandResult(success=True, message="Help text"),
            description="Show help",
        )
        executed: list[CommandExecuted] = []

        class CapturingApp(MessageInputApp):
            def on_command_executed(self, event: CommandExecuted) -> None:
                executed.append(event)

        app = CapturingApp(registry=registry)
        async with app.run_test() as pilot:
            inp = app.query_one("#message-input")
            inp.value = "/help"
            await inp.action_submit()
            await pilot.pause()
            assert len(executed) == 1
            assert executed[0].result.success is True
            assert executed[0].result.message == "Help text"

    @pytest.mark.asyncio
    async def test_slash_command_posts_command_executed_not_message_submitted(self) -> None:
        registry = CommandRegistry()
        registry.register(
            "help",
            lambda: CommandResult(success=True, message="Help text"),
            description="Show help",
        )
        messages: list[MessageSubmitted] = []
        executed: list[CommandExecuted] = []

        class CapturingApp(MessageInputApp):
            def on_message_submitted(self, event: MessageSubmitted) -> None:
                messages.append(event)

            def on_command_executed(self, event: CommandExecuted) -> None:
                executed.append(event)

        app = CapturingApp(registry=registry)
        async with app.run_test() as pilot:
            inp = app.query_one("#message-input")
            inp.value = "/help"
            await inp.action_submit()
            await pilot.pause()
            assert len(messages) == 0
            assert len(executed) == 1

    @pytest.mark.asyncio
    async def test_input_cleared_after_command_submit(self) -> None:
        registry = CommandRegistry()
        registry.register(
            "help",
            lambda: CommandResult(success=True, message="Help text"),
            description="Show help",
        )
        app = MessageInputApp(registry=registry)
        async with app.run_test() as pilot:
            inp = app.query_one("#message-input")
            inp.value = "/help"
            await inp.action_submit()
            await pilot.pause()
            assert inp.value == ""

    @pytest.mark.asyncio
    async def test_unknown_command_returns_failure(self) -> None:
        registry = CommandRegistry()
        executed: list[CommandExecuted] = []

        class CapturingApp(MessageInputApp):
            def on_command_executed(self, event: CommandExecuted) -> None:
                executed.append(event)

        app = CapturingApp(registry=registry)
        async with app.run_test() as pilot:
            inp = app.query_one("#message-input")
            inp.value = "/nonexistent"
            await inp.action_submit()
            await pilot.pause()
            assert len(executed) == 1
            assert executed[0].result.success is False

    @pytest.mark.asyncio
    async def test_command_executed_contains_original_command_text(self) -> None:
        registry = CommandRegistry()
        registry.register(
            "greet",
            lambda: CommandResult(success=True, message="Hi!"),
            description="Greet",
        )
        executed: list[CommandExecuted] = []

        class CapturingApp(MessageInputApp):
            def on_command_executed(self, event: CommandExecuted) -> None:
                executed.append(event)

        app = CapturingApp(registry=registry)
        async with app.run_test() as pilot:
            inp = app.query_one("#message-input")
            inp.value = "/greet"
            await inp.action_submit()
            await pilot.pause()
            assert executed[0].command == "/greet"


# --------------------------------------------------------------------------- #
# Tab accepts autocomplete suggestion
# --------------------------------------------------------------------------- #


class TestTabAcceptsSuggestion:
    """Pressing Tab should accept the autocomplete suggestion."""

    @pytest.mark.asyncio
    async def test_tab_accepts_suggestion_into_value(self) -> None:
        """When a suggestion is showing, Tab fills the input with it."""
        from textual.widgets import Input

        registry = CommandRegistry()
        registry.register(
            "models", lambda: CommandResult(success=True), "Open model picker"
        )
        registry.register(
            "help", lambda: CommandResult(success=True), "Show help"
        )

        app = MessageInputApp(registry=registry)
        async with app.run_test() as pilot:
            inp = app.query_one("#message-input", Input)
            # Type "/mo" — should trigger suggestion "/models"
            inp.value = "/mo"
            inp.cursor_position = len(inp.value)
            await pilot.pause()
            # Wait for the suggester to produce a suggestion
            await pilot.pause()

            # Press Tab to accept the suggestion
            await pilot.press("tab")
            await pilot.pause()
            assert inp.value == "/models"

    @pytest.mark.asyncio
    async def test_tab_without_suggestion_does_not_alter_value(self) -> None:
        """When no suggestion is showing, Tab does not change the value."""
        from textual.widgets import Input

        app = MessageInputApp()
        async with app.run_test() as pilot:
            inp = app.query_one("#message-input", Input)
            inp.value = "hello"
            inp.cursor_position = len(inp.value)
            await pilot.pause()

            await pilot.press("tab")
            await pilot.pause()
            # Value should remain unchanged
            assert inp.value == "hello"
