"""Slash-command registry for the TUI input bar.

Includes ``CommandRegistry`` (pure logic) and ``SlashCommandSuggester``
(Textual ``Suggester`` subclass for autocomplete).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from textual.suggester import Suggester


@dataclass
class CommandResult:
    """Outcome of executing a slash command."""

    success: bool
    message: str = ""


class CommandRegistry:
    """Registry for ``/slash`` commands that the user can type."""

    def __init__(self) -> None:
        self._commands: dict[str, Callable[..., CommandResult]] = {}
        self._descriptions: dict[str, str] = {}

    def register(
        self,
        name: str,
        handler: Callable[..., CommandResult],
        description: str = "",
    ) -> None:
        """Register a slash command.

        *name* should **not** include the leading ``/``.
        """
        self._commands[name] = handler
        self._descriptions[name] = description

    def dispatch(self, input_text: str) -> CommandResult:
        """Parse and dispatch a slash command from user input."""
        if not self.is_command(input_text):
            return CommandResult(success=False, message="Not a command")

        name, args = self.parse(input_text)
        handler = self._commands.get(name)
        if handler is None:
            return CommandResult(success=False, message=f"Unknown command: /{name}")

        return handler(*args)

    def is_command(self, input_text: str) -> bool:
        """Return True if *input_text* starts with ``/``."""
        return input_text.strip().startswith("/")

    def list_commands(self) -> dict[str, str]:
        """Return ``{name: description}`` for all registered commands."""
        return dict(self._descriptions)

    def parse(self, input_text: str) -> tuple[str, list[str]]:
        """Parse ``'/command arg1 arg2'`` into ``('command', ['arg1', 'arg2'])``."""
        parts = input_text.strip().split()
        name = parts[0].lstrip("/") if parts else ""
        args = parts[1:] if len(parts) > 1 else []
        return name, args


# --------------------------------------------------------------------------- #
# Autocomplete suggester
# --------------------------------------------------------------------------- #


class SlashCommandSuggester(Suggester):
    """Suggests slash commands when the user types ``/``.

    Only activates when the input value starts with ``/``.  Returns the
    first matching command (sorted alphabetically) or ``None``.
    """

    def __init__(
        self,
        commands: Iterable[str],
        *,
        case_sensitive: bool = False,
    ) -> None:
        super().__init__(use_cache=True, case_sensitive=case_sensitive)
        self._commands = sorted(commands)
        self._for_comparison = (
            self._commands
            if case_sensitive
            else [cmd.casefold() for cmd in self._commands]
        )

    @classmethod
    def from_registry(cls, registry: CommandRegistry) -> SlashCommandSuggester:
        """Create a suggester from a :class:`CommandRegistry`."""
        commands = [f"/{name}" for name in registry.list_commands()]
        return cls(commands)

    async def get_suggestion(self, value: str) -> str | None:
        """Return a completion suggestion for *value*, or ``None``."""
        if not value.startswith("/"):
            return None
        for idx, candidate in enumerate(self._for_comparison):
            if candidate.startswith(value if self.case_sensitive else value.casefold()):
                return self._commands[idx]
        return None
