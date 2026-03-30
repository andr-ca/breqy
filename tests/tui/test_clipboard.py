"""Tests for breqy.tui.clipboard — system clipboard fallback.

Verifies that copy_to_system_clipboard tries platform-appropriate
clipboard tools (xclip, xsel, wl-copy, pbcopy) and handles failures
gracefully without raising exceptions.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from breqy.tui.clipboard import copy_to_system_clipboard


class TestCopyToSystemClipboard:
    """copy_to_system_clipboard must push text via subprocess."""

    def test_calls_first_available_tool(self) -> None:
        """Should invoke the first available clipboard tool with the text."""
        with patch("breqy.tui.clipboard.subprocess.run") as mock_run:
            mock_run.return_value = None
            copy_to_system_clipboard("hello")

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            # Text piped via stdin
            assert call_args.kwargs.get("input") == "hello"

    def test_tries_next_tool_on_file_not_found(self) -> None:
        """When the first tool is missing, fall through to the next."""
        call_log: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            call_log.append(cmd)
            if len(call_log) == 1:
                raise FileNotFoundError(f"{cmd[0]} not found")

        with patch("breqy.tui.clipboard.subprocess.run", side_effect=fake_run):
            copy_to_system_clipboard("fallback text")

        assert len(call_log) >= 2, "Should have tried at least two tools"

    def test_no_exception_when_all_tools_missing(self) -> None:
        """If every clipboard tool is missing, fail silently."""
        with patch(
            "breqy.tui.clipboard.subprocess.run",
            side_effect=FileNotFoundError("not found"),
        ):
            # Must not raise
            copy_to_system_clipboard("no clipboard")

    def test_no_exception_on_subprocess_error(self) -> None:
        """If a tool crashes, fail silently."""
        import subprocess

        with patch(
            "breqy.tui.clipboard.subprocess.run",
            side_effect=subprocess.SubprocessError("broken"),
        ):
            copy_to_system_clipboard("broken clipboard")

    def test_empty_string_is_a_noop(self) -> None:
        """Empty text should not invoke any subprocess."""
        with patch("breqy.tui.clipboard.subprocess.run") as mock_run:
            copy_to_system_clipboard("")
            mock_run.assert_not_called()
