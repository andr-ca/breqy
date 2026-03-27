"""Tests for breqy.tui.commands — CommandRegistry."""
from __future__ import annotations

import pytest

from breqy.tui.commands import CommandRegistry, CommandResult


class TestCommandResultDataclass:
    """Test CommandResult dataclass."""

    def test_creates_success_result(self) -> None:
        result = CommandResult(success=True, message="Done")
        assert result.success is True
        assert result.message == "Done"

    def test_default_message_is_empty(self) -> None:
        result = CommandResult(success=False)
        assert result.message == ""


class TestCommandRegistryInit:
    """Test CommandRegistry initialization."""

    def test_creates_empty_registry(self) -> None:
        registry = CommandRegistry()
        assert registry.list_commands() == {}


class TestCommandRegistryRegister:
    """Test command registration."""

    def test_registers_command(self) -> None:
        registry = CommandRegistry()
        registry.register("help", lambda: CommandResult(success=True), description="Show help")
        commands = registry.list_commands()
        assert "help" in commands
        assert commands["help"] == "Show help"

    def test_registers_multiple_commands(self) -> None:
        registry = CommandRegistry()
        registry.register("help", lambda: CommandResult(success=True), description="Show help")
        registry.register("quit", lambda: CommandResult(success=True), description="Quit session")
        commands = registry.list_commands()
        assert len(commands) == 2


class TestCommandRegistryIsCommand:
    """Test slash command detection."""

    def test_recognizes_slash_prefix(self) -> None:
        registry = CommandRegistry()
        assert registry.is_command("/help") is True

    def test_rejects_non_slash_input(self) -> None:
        registry = CommandRegistry()
        assert registry.is_command("hello") is False

    def test_rejects_empty_input(self) -> None:
        registry = CommandRegistry()
        assert registry.is_command("") is False

    def test_rejects_whitespace_only(self) -> None:
        registry = CommandRegistry()
        assert registry.is_command("   ") is False


class TestCommandRegistryParse:
    """Test command parsing."""

    def test_parses_simple_command(self) -> None:
        registry = CommandRegistry()
        name, args = registry.parse("/help")
        assert name == "help"
        assert args == []

    def test_parses_command_with_args(self) -> None:
        registry = CommandRegistry()
        name, args = registry.parse("/send hello world")
        assert name == "send"
        assert args == ["hello", "world"]

    def test_strips_whitespace(self) -> None:
        registry = CommandRegistry()
        name, args = registry.parse("  /help  ")
        assert name == "help"
        assert args == []

    def test_parses_command_with_extra_spaces_between_args(self) -> None:
        registry = CommandRegistry()
        name, args = registry.parse("/send   hello   world")
        assert name == "send"
        assert args == ["hello", "world"]


class TestCommandRegistryDispatch:
    """Test command dispatching."""

    def test_dispatches_to_registered_handler(self) -> None:
        registry = CommandRegistry()
        registry.register(
            "greet",
            lambda: CommandResult(success=True, message="Hello!"),
            description="Greet",
        )
        result = registry.dispatch("/greet")
        assert result.success is True
        assert result.message == "Hello!"

    def test_dispatches_with_args(self) -> None:
        registry = CommandRegistry()

        def echo_handler(*args: str) -> CommandResult:
            return CommandResult(success=True, message=" ".join(args))

        registry.register("echo", echo_handler, description="Echo args")
        result = registry.dispatch("/echo hello world")
        assert result.success is True
        assert result.message == "hello world"

    def test_returns_failure_for_unknown_command(self) -> None:
        registry = CommandRegistry()
        result = registry.dispatch("/nonexistent")
        assert result.success is False

    def test_returns_failure_for_non_command_input(self) -> None:
        registry = CommandRegistry()
        result = registry.dispatch("just text")
        assert result.success is False
