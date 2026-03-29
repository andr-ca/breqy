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


# --------------------------------------------------------------------------- #
# SlashCommandSuggester (autocomplete)
# --------------------------------------------------------------------------- #


class TestSlashCommandSuggester:
    """Tests for SlashCommandSuggester — autocomplete for slash commands."""

    @pytest.mark.asyncio
    async def test_suggests_matching_command(self) -> None:
        """Typing '/mo' should suggest '/models'."""
        from breqy.tui.commands import SlashCommandSuggester

        suggester = SlashCommandSuggester(["/models", "/help"])
        result = await suggester.get_suggestion("/mo")
        assert result == "/models"

    @pytest.mark.asyncio
    async def test_suggests_nothing_for_non_slash_input(self) -> None:
        """Normal text (no slash prefix) should not trigger suggestions."""
        from breqy.tui.commands import SlashCommandSuggester

        suggester = SlashCommandSuggester(["/models", "/help"])
        result = await suggester.get_suggestion("hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_suggests_nothing_for_empty_input(self) -> None:
        """Empty input should not trigger suggestions."""
        from breqy.tui.commands import SlashCommandSuggester

        suggester = SlashCommandSuggester(["/models", "/help"])
        result = await suggester.get_suggestion("")
        assert result is None

    @pytest.mark.asyncio
    async def test_suggests_first_match_for_slash_only(self) -> None:
        """Typing just '/' should suggest the first command alphabetically."""
        from breqy.tui.commands import SlashCommandSuggester

        suggester = SlashCommandSuggester(["/help", "/models"])
        result = await suggester.get_suggestion("/")
        assert result == "/help"

    @pytest.mark.asyncio
    async def test_suggests_help_for_slash_h(self) -> None:
        """Typing '/h' should suggest '/help'."""
        from breqy.tui.commands import SlashCommandSuggester

        suggester = SlashCommandSuggester(["/models", "/help"])
        result = await suggester.get_suggestion("/h")
        assert result == "/help"

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self) -> None:
        """Typing '/z' with no matching commands should return None."""
        from breqy.tui.commands import SlashCommandSuggester

        suggester = SlashCommandSuggester(["/models", "/help"])
        result = await suggester.get_suggestion("/z")
        assert result is None

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self) -> None:
        """Matching should be case-insensitive by default."""
        from breqy.tui.commands import SlashCommandSuggester

        suggester = SlashCommandSuggester(["/Models", "/Help"])
        result = await suggester.get_suggestion("/mo")
        assert result == "/Models"

    @pytest.mark.asyncio
    async def test_exact_match_returns_command(self) -> None:
        """Typing the full command '/models' should still return it."""
        from breqy.tui.commands import SlashCommandSuggester

        suggester = SlashCommandSuggester(["/models", "/help"])
        result = await suggester.get_suggestion("/models")
        assert result == "/models"

    def test_is_textual_suggester_subclass(self) -> None:
        """SlashCommandSuggester should be a Textual Suggester subclass."""
        from textual.suggester import Suggester

        from breqy.tui.commands import SlashCommandSuggester

        assert issubclass(SlashCommandSuggester, Suggester)

    @pytest.mark.asyncio
    async def test_from_registry_creates_suggester(self) -> None:
        """from_registry class method creates a suggester from a CommandRegistry."""
        from breqy.tui.commands import SlashCommandSuggester

        registry = CommandRegistry()
        registry.register("models", lambda: CommandResult(success=True), "Open model picker")
        registry.register("help", lambda: CommandResult(success=True), "Show help")

        suggester = SlashCommandSuggester.from_registry(registry)
        result = await suggester.get_suggestion("/mo")
        assert result == "/models"


class TestMessageInputHasSuggester:
    """Tests that MessageInput uses SlashCommandSuggester for autocomplete."""

    @pytest.mark.asyncio
    async def test_message_input_inner_input_has_suggester(self) -> None:
        """The inner Input widget should have a SlashCommandSuggester set."""
        from textual.app import App, ComposeResult

        from breqy.tui.commands import SlashCommandSuggester
        from breqy.tui.widgets.message_input import MessageInput

        registry = CommandRegistry()
        registry.register("models", lambda: CommandResult(success=True), "Model picker")

        class TestApp(App[None]):
            def compose(self) -> ComposeResult:
                yield MessageInput(command_registry=registry)

        app = TestApp()
        async with app.run_test() as pilot:
            mi = app.query_one(MessageInput)
            inner_input = mi.query_one("#message-input")
            assert isinstance(inner_input.suggester, SlashCommandSuggester)


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
