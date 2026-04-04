"""Unit tests for /logs slash command registration and dispatch.

Verifies that:
- ``/logs`` is registered in the ChatScreen command registry
- Dispatching ``/logs`` returns ``CommandResult(success=True, message="logs")``
"""

from __future__ import annotations

import pytest

from breqy.tui.commands import CommandRegistry, CommandResult
from breqy.tui.screens.chat import ChatScreen


class TestLogsCommandRegistered:
    """CommandRegistry recognises /logs without error."""

    def test_logs_command_registered(self) -> None:
        """The /logs command must be present in the chat registry."""
        registry = ChatScreen._build_command_registry()
        commands = registry.list_commands()
        assert "logs" in commands

    def test_logs_command_returns_logs_token(self) -> None:
        """dispatch('/logs') returns CommandResult(success=True, message='logs')."""
        registry = ChatScreen._build_command_registry()
        result = registry.dispatch("/logs")
        assert result.success is True
        assert result.message == "logs"
