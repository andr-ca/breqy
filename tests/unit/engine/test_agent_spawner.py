"""Tests for AgentSpawner."""
from __future__ import annotations

import signal
import sys
from unittest.mock import MagicMock, patch

import pytest

from breqy.engine.agent_spawner import AgentSpawner, SpawnedAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_process(*, pid: int = 100, alive: bool = True) -> MagicMock:
    """Return a mock subprocess.Popen with controllable poll() and pid."""
    proc = MagicMock()
    proc.pid = pid
    proc.poll.return_value = None if alive else 0
    return proc


# ---------------------------------------------------------------------------
# Existing tests (preserved)
# ---------------------------------------------------------------------------


def test_spawner_builds_command():
    """_build_command() returns a valid python -m invocation."""
    spawner = AgentSpawner(engine_socket="/tmp/test.sock")
    cmd = spawner._build_command("system/agents/breqy")
    assert sys.executable == cmd[0]
    assert "-m" in cmd
    assert "breqy.agents.runtime" in cmd


def test_spawner_tracks_no_processes_initially():
    """list_running() returns empty list before any spawns."""
    spawner = AgentSpawner(engine_socket="/tmp/test.sock")
    assert spawner.list_running() == []


# ---------------------------------------------------------------------------
# SpawnedAgent session_id field
# ---------------------------------------------------------------------------


class TestSpawnedAgentSessionField:
    def test_spawned_agent_has_session_id_default_empty(self) -> None:
        """SpawnedAgent defaults session_id to empty string."""
        proc = _make_mock_process()
        agent = SpawnedAgent(agent_dir="agents/a", process=proc)
        assert agent.session_id == ""

    def test_spawned_agent_stores_session_id(self) -> None:
        """SpawnedAgent stores an explicit session_id."""
        proc = _make_mock_process()
        agent = SpawnedAgent(
            agent_dir="agents/a", process=proc, session_id="sess-1"
        )
        assert agent.session_id == "sess-1"


# ---------------------------------------------------------------------------
# spawn() with session_id
# ---------------------------------------------------------------------------


class TestSpawnWithSession:
    @patch("breqy.engine.agent_spawner.subprocess.Popen")
    def test_spawn_without_session_id_backward_compat(
        self, mock_popen: MagicMock
    ) -> None:
        """spawn() works without session_id (backward compatible)."""
        mock_popen.return_value = _make_mock_process(pid=42)
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")

        pid = spawner.spawn("agents/a")

        assert pid == 42
        assert spawner.is_running("agents/a")
        # Verify session_id defaulted to ""
        assert spawner._processes["agents/a"].session_id == ""

    @patch("breqy.engine.agent_spawner.subprocess.Popen")
    def test_spawn_with_session_id(self, mock_popen: MagicMock) -> None:
        """spawn() stores session_id when provided."""
        mock_popen.return_value = _make_mock_process(pid=43)
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")

        pid = spawner.spawn("agents/b", session_id="sess-99")

        assert pid == 43
        assert spawner._processes["agents/b"].session_id == "sess-99"


# ---------------------------------------------------------------------------
# force_kill()
# ---------------------------------------------------------------------------


class TestForceKill:
    @patch("breqy.engine.agent_spawner.subprocess.Popen")
    def test_force_kill_sends_sigkill(self, mock_popen: MagicMock) -> None:
        """force_kill() sends SIGKILL and removes from _processes."""
        proc = _make_mock_process(pid=10)
        mock_popen.return_value = proc
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")
        spawner.spawn("agents/a")

        spawner.force_kill("agents/a")

        proc.send_signal.assert_called_once_with(signal.SIGKILL)
        assert "agents/a" not in spawner._processes

    @patch("breqy.engine.agent_spawner.subprocess.Popen")
    def test_force_kill_already_dead_does_not_signal(
        self, mock_popen: MagicMock
    ) -> None:
        """force_kill() on an already-dead process does not send signal."""
        proc = _make_mock_process(pid=11, alive=False)
        mock_popen.return_value = proc
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")
        spawner.spawn("agents/a")

        spawner.force_kill("agents/a")

        proc.send_signal.assert_not_called()
        assert "agents/a" not in spawner._processes

    def test_force_kill_unknown_agent_is_noop(self) -> None:
        """force_kill() on an unknown agent_dir does nothing."""
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")
        # Should not raise
        spawner.force_kill("agents/nonexistent")


# ---------------------------------------------------------------------------
# force_kill_all()
# ---------------------------------------------------------------------------


class TestForceKillAll:
    @patch("breqy.engine.agent_spawner.subprocess.Popen")
    def test_force_kill_all_sigkills_every_running(
        self, mock_popen: MagicMock
    ) -> None:
        """force_kill_all() sends SIGKILL to all running agents."""
        proc_a = _make_mock_process(pid=20)
        proc_b = _make_mock_process(pid=21)
        mock_popen.side_effect = [proc_a, proc_b]
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")
        spawner.spawn("agents/a")
        spawner.spawn("agents/b")

        spawner.force_kill_all()

        proc_a.send_signal.assert_called_once_with(signal.SIGKILL)
        proc_b.send_signal.assert_called_once_with(signal.SIGKILL)
        assert spawner._processes == {}


# ---------------------------------------------------------------------------
# kill_by_session()
# ---------------------------------------------------------------------------


class TestKillBySession:
    @patch("breqy.engine.agent_spawner.subprocess.Popen")
    def test_kill_by_session_only_kills_matching(
        self, mock_popen: MagicMock
    ) -> None:
        """kill_by_session() terminates only agents with matching session."""
        proc_a = _make_mock_process(pid=30)
        proc_b = _make_mock_process(pid=31)
        proc_c = _make_mock_process(pid=32)
        mock_popen.side_effect = [proc_a, proc_b, proc_c]
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")
        spawner.spawn("agents/a", session_id="sess-1")
        spawner.spawn("agents/b", session_id="sess-2")
        spawner.spawn("agents/c", session_id="sess-1")

        spawner.kill_by_session("sess-1")

        proc_a.terminate.assert_called_once()
        proc_c.terminate.assert_called_once()
        proc_b.terminate.assert_not_called()
        # agents/b should still be tracked
        assert "agents/b" in spawner._processes
        assert "agents/a" not in spawner._processes
        assert "agents/c" not in spawner._processes

    def test_kill_by_session_no_match_is_noop(self) -> None:
        """kill_by_session() with unknown session does nothing."""
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")
        spawner.kill_by_session("no-such-session")


# ---------------------------------------------------------------------------
# force_kill_by_session()
# ---------------------------------------------------------------------------


class TestForceKillBySession:
    @patch("breqy.engine.agent_spawner.subprocess.Popen")
    def test_force_kill_by_session_sigkills_matching(
        self, mock_popen: MagicMock
    ) -> None:
        """force_kill_by_session() sends SIGKILL to matching session only."""
        proc_a = _make_mock_process(pid=40)
        proc_b = _make_mock_process(pid=41)
        mock_popen.side_effect = [proc_a, proc_b]
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")
        spawner.spawn("agents/a", session_id="sess-x")
        spawner.spawn("agents/b", session_id="sess-y")

        spawner.force_kill_by_session("sess-x")

        proc_a.send_signal.assert_called_once_with(signal.SIGKILL)
        proc_b.send_signal.assert_not_called()
        assert "agents/a" not in spawner._processes
        assert "agents/b" in spawner._processes


# ---------------------------------------------------------------------------
# list_by_session()
# ---------------------------------------------------------------------------


class TestListBySession:
    @patch("breqy.engine.agent_spawner.subprocess.Popen")
    def test_list_by_session_returns_matching(
        self, mock_popen: MagicMock
    ) -> None:
        """list_by_session() returns SpawnedAgent objects for the session."""
        proc_a = _make_mock_process(pid=50)
        proc_b = _make_mock_process(pid=51)
        proc_c = _make_mock_process(pid=52)
        mock_popen.side_effect = [proc_a, proc_b, proc_c]
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")
        spawner.spawn("agents/a", session_id="sess-1")
        spawner.spawn("agents/b", session_id="sess-2")
        spawner.spawn("agents/c", session_id="sess-1")

        result = spawner.list_by_session("sess-1")

        assert len(result) == 2
        dirs = [s.agent_dir for s in result]
        assert "agents/a" in dirs
        assert "agents/c" in dirs

    def test_list_by_session_empty_when_no_match(self) -> None:
        """list_by_session() returns empty list when no agents match."""
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")
        assert spawner.list_by_session("nonexistent") == []


# ---------------------------------------------------------------------------
# _build_command() includes --session-id
# ---------------------------------------------------------------------------


class TestBuildCommandSessionId:
    def test_build_command_includes_session_id_when_provided(self) -> None:
        """_build_command() includes --session-id when session_id is passed."""
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")
        cmd = spawner._build_command("agents/breqy", session_id="ses_abc123")
        assert "--session-id" in cmd
        idx = cmd.index("--session-id")
        assert cmd[idx + 1] == "ses_abc123"

    def test_build_command_omits_session_id_when_empty(self) -> None:
        """_build_command() does not include --session-id when empty."""
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")
        cmd = spawner._build_command("agents/breqy")
        assert "--session-id" not in cmd

    def test_spawn_passes_session_id_to_build_command(self) -> None:
        """spawn() passes session_id through to _build_command()."""
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")
        built_commands: list[tuple[str, str]] = []

        original_build = spawner._build_command

        def tracking_build(agent_dir: str, session_id: str = "") -> list[str]:
            built_commands.append((agent_dir, session_id))
            return original_build(agent_dir, session_id=session_id)

        spawner._build_command = tracking_build  # type: ignore[method-assign]

        with patch("breqy.engine.agent_spawner.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _make_mock_process(pid=77)
            spawner.spawn("agents/breqy", session_id="ses_test")

        assert len(built_commands) == 1
        assert built_commands[0] == ("agents/breqy", "ses_test")


# ---------------------------------------------------------------------------
# Observability: Task 7 — subprocess DEVNULL
# ---------------------------------------------------------------------------


class TestSpawnUsesDevnull:
    @patch("breqy.engine.agent_spawner.subprocess.Popen")
    def test_spawn_uses_devnull_for_stdout_and_stderr(
        self, mock_popen: MagicMock
    ) -> None:
        """spawn() should use DEVNULL for stdout and stderr (not PIPE)."""
        import subprocess as _subprocess

        mock_popen.return_value = _make_mock_process(pid=200)
        spawner = AgentSpawner(engine_socket="/tmp/test.sock")

        spawner.spawn("agents/breqy", session_id="ses_1")

        call_kwargs = mock_popen.call_args
        assert call_kwargs[1]["stdout"] == _subprocess.DEVNULL, (
            "stdout must be DEVNULL to avoid pipe buffer hang"
        )
        assert call_kwargs[1]["stderr"] == _subprocess.DEVNULL, (
            "stderr must be DEVNULL to avoid pipe buffer hang"
        )
