"""Unit tests for AgentLogsScreen — agent log file tailing overlay.

These tests target the pure helper utilities exposed by the screen module:
  - ``resolve_agent_log_path(agent_id, data_dir_env)``
  - ``read_tail(path, n)``

Plus one Textual pilot test for the "file not found → placeholder" behaviour.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helper: resolve_agent_log_path
# ---------------------------------------------------------------------------


class TestResolveAgentLogPath:
    """resolve_agent_log_path respects BREQY_DATA_DIR env var and agent_id."""

    def test_resolves_log_path_from_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BREQY_DATA_DIR env var produces the correct resolved path."""
        from breqy.tui.screens.agent_logs import resolve_agent_log_path

        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path))
        result = resolve_agent_log_path("breqy")
        assert result == tmp_path / "logs" / "agent-breqy.log"

    def test_resolves_default_path_without_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without BREQY_DATA_DIR, defaults to ~/.breqy/data/logs/agent-{id}.log."""
        from breqy.tui.screens.agent_logs import resolve_agent_log_path

        monkeypatch.delenv("BREQY_DATA_DIR", raising=False)
        result = resolve_agent_log_path("breqy")
        expected = Path("~/.breqy/data").expanduser() / "logs" / "agent-breqy.log"
        assert result == expected

    def test_fallback_agent_id_produces_agent_log(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty agent_id falls back to agent.log (no-ID convention)."""
        from breqy.tui.screens.agent_logs import resolve_agent_log_path

        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path))
        result = resolve_agent_log_path("")
        assert result == tmp_path / "logs" / "agent.log"


# ---------------------------------------------------------------------------
# Helper: read_tail
# ---------------------------------------------------------------------------


class TestReadTail:
    """read_tail returns the last N lines from a file, or a placeholder."""

    def test_reads_last_n_lines_on_open(self, tmp_path: Path) -> None:
        """Seed temp file with 300 lines; confirm only last 200 returned."""
        from breqy.tui.screens.agent_logs import read_tail

        log_file = tmp_path / "agent-test.log"
        lines = [f"line {i}\n" for i in range(300)]
        log_file.write_text("".join(lines), encoding="utf-8")

        result = read_tail(log_file, n=200)
        result_lines = result.splitlines()
        assert len(result_lines) == 200
        assert result_lines[0] == "line 100"
        assert result_lines[-1] == "line 299"

    def test_returns_all_lines_when_fewer_than_n(self, tmp_path: Path) -> None:
        """When fewer than N lines exist, all lines are returned."""
        from breqy.tui.screens.agent_logs import read_tail

        log_file = tmp_path / "agent-test.log"
        log_file.write_text("line 0\nline 1\nline 2\n", encoding="utf-8")

        result = read_tail(log_file, n=200)
        assert result.splitlines() == ["line 0", "line 1", "line 2"]

    def test_file_not_found_shows_placeholder(self, tmp_path: Path) -> None:
        """Non-existent path returns the waiting placeholder string; no crash."""
        from breqy.tui.screens.agent_logs import read_tail

        missing = tmp_path / "no-such-file.log"
        result = read_tail(missing, n=200)
        assert "Waiting" in result or "waiting" in result

    def test_empty_file_returns_empty_string(self, tmp_path: Path) -> None:
        """Empty log file returns empty string, not an error."""
        from breqy.tui.screens.agent_logs import read_tail

        log_file = tmp_path / "agent-test.log"
        log_file.write_text("", encoding="utf-8")

        result = read_tail(log_file, n=200)
        assert result == ""


# ---------------------------------------------------------------------------
# Poll helper: read_new_lines
# ---------------------------------------------------------------------------


class TestReadNewLines:
    """read_new_lines returns only bytes written after a given offset."""

    def test_polls_new_lines(self, tmp_path: Path) -> None:
        """Write initial lines, get offset, write more, confirm new lines returned."""
        from breqy.tui.screens.agent_logs import read_new_lines

        log_file = tmp_path / "agent-test.log"
        log_file.write_text("line 0\nline 1\n", encoding="utf-8")

        # Read initial state, recording the offset
        initial_offset = log_file.stat().st_size
        assert initial_offset > 0

        # Append new lines
        with log_file.open("a", encoding="utf-8") as f:
            f.write("line 2\nline 3\n")

        new_text, new_offset = read_new_lines(log_file, initial_offset)
        assert "line 2" in new_text
        assert "line 3" in new_text
        assert new_offset > initial_offset

    def test_file_disappears_and_reappears(self, tmp_path: Path) -> None:
        """File deleted mid-session: OSError caught silently; offset unchanged."""
        from breqy.tui.screens.agent_logs import read_new_lines

        log_file = tmp_path / "agent-test.log"
        log_file.write_text("line 0\n", encoding="utf-8")
        offset = log_file.stat().st_size

        # Delete the file (simulate agent restart)
        log_file.unlink()

        new_text, new_offset = read_new_lines(log_file, offset)
        assert new_text == ""
        assert new_offset == offset  # offset unchanged on error

        # File reappears — should resume from offset 0 since file is new
        log_file.write_text("new content\n", encoding="utf-8")
        new_text2, new_offset2 = read_new_lines(log_file, 0)
        assert "new content" in new_text2
        assert new_offset2 > 0


# ---------------------------------------------------------------------------
# Pure helper: filter_lines
# ---------------------------------------------------------------------------


class TestFilterLines:
    """filter_lines returns only lines containing the filter substring."""

    def test_filter_lines_hides_non_matching(self) -> None:
        """Lines not containing the filter string are excluded."""
        from breqy.tui.screens.agent_logs import filter_lines

        lines = ["info: provider started", "debug: tool called", "info: stream ended"]
        result = filter_lines(lines, "info")
        assert result == ["info: provider started", "info: stream ended"]

    def test_filter_lines_empty_returns_all(self) -> None:
        """Empty filter string returns all lines unchanged."""
        from breqy.tui.screens.agent_logs import filter_lines

        lines = ["line a", "line b", "line c"]
        result = filter_lines(lines, "")
        assert result == ["line a", "line b", "line c"]

    def test_filter_lines_is_case_insensitive(self) -> None:
        """Lowercase filter matches uppercase content and vice versa."""
        from breqy.tui.screens.agent_logs import filter_lines

        lines = ["INFO: started", "DEBUG: called", "WARNING: slow"]
        result = filter_lines(lines, "info")
        assert result == ["INFO: started"]

    def test_filter_lines_partial_match(self) -> None:
        """Substring match — does not require full-line equality."""
        from breqy.tui.screens.agent_logs import filter_lines

        lines = [
            '{"event": "llm_call", "initiator": "user"}',
            '{"event": "tool_result", "initiator": "agent"}',
        ]
        result = filter_lines(lines, "initiator")
        assert len(result) == 2

    def test_filter_lines_no_matches_returns_empty(self) -> None:
        """Filter with no matches returns an empty list."""
        from breqy.tui.screens.agent_logs import filter_lines

        lines = ["alpha", "beta", "gamma"]
        result = filter_lines(lines, "zzz")
        assert result == []
