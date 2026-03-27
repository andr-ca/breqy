"""Slash-command registry for the TUI input bar.

Pure logic — no Textual dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


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
