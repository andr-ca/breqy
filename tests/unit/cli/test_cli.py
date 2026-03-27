"""Tests for breqy CLI entry point."""
from __future__ import annotations

import os
import signal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from breqy.cli import (
    _load_dotenv,
    _pid_file_path,
    _read_pid,
    _remove_pid,
    _write_pid,
    main,
)


# ---------------------------------------------------------------------------
# PID file helpers
# ---------------------------------------------------------------------------


class TestPidFileHelpers:
    """Tests for PID file read/write/remove helpers."""

    def test_write_pid_creates_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path))
        _write_pid(42)
        pid_file = tmp_path / "engine.pid"
        assert pid_file.exists()
        assert pid_file.read_text() == "42"

    def test_read_pid_returns_written_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path))
        _write_pid(12345)
        assert _read_pid() == 12345

    def test_read_pid_returns_none_when_no_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path / "nonexistent"))
        assert _read_pid() is None

    def test_read_pid_returns_none_for_corrupt_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path))
        pid_file = tmp_path / "engine.pid"
        pid_file.write_text("not-a-number")
        assert _read_pid() is None

    def test_remove_pid_deletes_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path))
        _write_pid(99)
        assert (tmp_path / "engine.pid").exists()
        _remove_pid()
        assert not (tmp_path / "engine.pid").exists()

    def test_remove_pid_no_error_when_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path / "nonexistent"))
        _remove_pid()  # Should not raise

    def test_pid_file_path_uses_env_data_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", "/custom/data")
        assert _pid_file_path() == Path("/custom/data/engine.pid").resolve()

    def test_pid_file_path_uses_default_when_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BREQY_DATA_DIR", raising=False)
        expected = (Path.home() / ".breqy" / "data" / "engine.pid").resolve()
        assert _pid_file_path() == expected

    def test_pid_file_path_expands_tilde(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", "~/.local/share/breqy")
        result = _pid_file_path()
        assert "~" not in str(result)
        assert result == (Path.home() / ".local" / "share" / "breqy" / "engine.pid").resolve()

    def test_write_pid_creates_parent_dirs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        nested = tmp_path / "deep" / "nested" / "dir"
        monkeypatch.setenv("BREQY_DATA_DIR", str(nested))
        _write_pid(777)
        assert (nested / "engine.pid").read_text() == "777"


# ---------------------------------------------------------------------------
# CLI group / version
# ---------------------------------------------------------------------------


class TestCliGroup:
    """Tests for the top-level CLI group."""

    def test_main_shows_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Breqy" in result.output
        assert "engine" in result.output
        assert "tui" in result.output
        assert "auth" in result.output

    def test_main_shows_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_engine_group_shows_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["engine", "--help"])
        assert result.exit_code == 0
        assert "start" in result.output
        assert "stop" in result.output
        assert "status" in result.output


# ---------------------------------------------------------------------------
# engine stop
# ---------------------------------------------------------------------------


class TestEngineStop:
    """Tests for `breqy engine stop`."""

    def test_stop_no_pid_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path / "empty"))
        runner = CliRunner()
        result = runner.invoke(main, ["engine", "stop"])
        assert result.exit_code != 0
        assert "No running engine" in result.output

    def test_stop_sends_sigterm(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path))
        _write_pid(os.getpid())  # Use our own PID (signal 0 is safe)

        killed_pids: list[tuple[int, int]] = []

        def mock_kill(pid: int, sig: int) -> None:
            killed_pids.append((pid, sig))

        monkeypatch.setattr(os, "kill", mock_kill)

        runner = CliRunner()
        result = runner.invoke(main, ["engine", "stop"])
        assert result.exit_code == 0
        assert "SIGTERM" in result.output
        assert len(killed_pids) == 1
        assert killed_pids[0][1] == signal.SIGTERM

    def test_stop_stale_pid_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path))
        _write_pid(999999)  # Almost certainly not a real PID

        def mock_kill(pid: int, sig: int) -> None:
            raise ProcessLookupError()

        monkeypatch.setattr(os, "kill", mock_kill)

        runner = CliRunner()
        result = runner.invoke(main, ["engine", "stop"])
        assert "not found" in result.output
        # PID file should be cleaned up
        assert not (tmp_path / "engine.pid").exists()

    def test_stop_permission_denied(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path))
        _write_pid(1)

        def mock_kill(pid: int, sig: int) -> None:
            raise PermissionError()

        monkeypatch.setattr(os, "kill", mock_kill)

        runner = CliRunner()
        result = runner.invoke(main, ["engine", "stop"])
        assert result.exit_code != 0
        assert "Permission denied" in result.output


# ---------------------------------------------------------------------------
# engine status
# ---------------------------------------------------------------------------


class TestEngineStatus:
    """Tests for `breqy engine status`."""

    def test_status_no_pid_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path / "empty"))
        runner = CliRunner()
        result = runner.invoke(main, ["engine", "status"])
        assert result.exit_code == 0
        assert "not running" in result.output

    def test_status_running(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path))
        my_pid = os.getpid()
        _write_pid(my_pid)

        runner = CliRunner()
        result = runner.invoke(main, ["engine", "status"])
        assert result.exit_code == 0
        assert "running" in result.output
        assert str(my_pid) in result.output

    def test_status_stale_pid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BREQY_DATA_DIR", str(tmp_path))
        _write_pid(999999)

        def mock_kill(pid: int, sig: int) -> None:
            raise ProcessLookupError()

        monkeypatch.setattr(os, "kill", mock_kill)

        runner = CliRunner()
        result = runner.invoke(main, ["engine", "status"])
        assert "not running" in result.output
        assert "stale" in result.output.lower()
        # PID file should be cleaned up
        assert not (tmp_path / "engine.pid").exists()


# ---------------------------------------------------------------------------
# engine start
# ---------------------------------------------------------------------------


class TestEngineStart:
    """Tests for `breqy engine start`."""

    def test_start_shows_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["engine", "start", "--help"])
        assert result.exit_code == 0
        assert "--socket" in result.output
        assert "--data-dir" in result.output
        assert "--log-level" in result.output
        assert "--no-agent" in result.output

    def test_start_cli_overrides_propagate_to_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLI flags --socket, --data-dir, --log-level set corresponding env vars."""
        captured_env: dict[str, str] = {}

        def fake_load_engine_config() -> SimpleNamespace:
            captured_env["socket"] = os.environ.get("BREQY_ENGINE_SOCKET", "")
            captured_env["data"] = os.environ.get("BREQY_DATA_DIR", "")
            captured_env["log"] = os.environ.get("BREQY_LOG_LEVEL", "")
            # Return a config-like object so we don't actually start
            raise SystemExit(0)

        monkeypatch.setattr("breqy.cli.load_engine_config", fake_load_engine_config, raising=False)
        # We need to patch at the import location inside engine_start
        with patch("breqy.config.loader.load_engine_config", fake_load_engine_config):
            runner = CliRunner()
            result = runner.invoke(
                main,
                [
                    "engine", "start",
                    "--socket", "/tmp/custom.sock",
                    "--data-dir", "/tmp/custom-data",
                    "--log-level", "DEBUG",
                    "--no-agent",
                ],
            )

        assert captured_env.get("socket") == "/tmp/custom.sock"
        assert captured_env.get("data") == "/tmp/custom-data"
        assert captured_env.get("log") == "DEBUG"


# ---------------------------------------------------------------------------
# tui
# ---------------------------------------------------------------------------


class TestTuiCommand:
    """Tests for `breqy tui`."""

    def test_tui_shows_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["tui", "--help"])
        assert result.exit_code == 0
        assert "--socket" in result.output

    def test_tui_invokes_breqy_app(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies that `breqy tui` creates BreqyApp with correct socket and calls run()."""
        app_mock = MagicMock()

        def fake_app(socket_path: str) -> MagicMock:
            app_mock.socket_path = socket_path
            return app_mock

        monkeypatch.setattr("breqy.tui.app.BreqyApp", fake_app)

        runner = CliRunner()
        result = runner.invoke(main, ["tui", "--socket", "/tmp/test-tui.sock"])
        assert result.exit_code == 0
        assert app_mock.socket_path == "/tmp/test-tui.sock"
        app_mock.run.assert_called_once()

    def test_tui_uses_env_socket_when_no_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without --socket, the TUI reads BREQY_ENGINE_SOCKET from env."""
        app_mock = MagicMock()

        def fake_app(socket_path: str) -> MagicMock:
            app_mock.socket_path = socket_path
            return app_mock

        monkeypatch.setattr("breqy.tui.app.BreqyApp", fake_app)
        monkeypatch.setenv("BREQY_ENGINE_SOCKET", "/tmp/env-socket.sock")

        runner = CliRunner()
        result = runner.invoke(main, ["tui"])
        assert result.exit_code == 0
        assert app_mock.socket_path == "/tmp/env-socket.sock"


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------


class TestAuthCommand:
    """Tests for `breqy auth <provider>`."""

    def test_auth_shows_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "--help"])
        assert result.exit_code == 0
        assert "copilot" in result.output

    def test_auth_rejects_unsupported_provider(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "openai"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output or "openai" in result.output

    def test_auth_accepts_valid_providers(self) -> None:
        """All valid provider names are recognized by click.Choice."""
        runner = CliRunner()
        for provider in ("copilot", "codex", "claude", "gemini", "qwen"):
            result = runner.invoke(main, ["auth", provider, "--help"])
            # --help is not valid for auth but the provider should be accepted
            # The command itself will fail trying to import/run, which is expected
            # We just verify the Choice validator didn't reject it
            assert "Invalid value" not in (result.output or "")


# ---------------------------------------------------------------------------
# dotenv loading
# ---------------------------------------------------------------------------


class TestDotenvLoading:
    """Tests for .env auto-loading."""

    def test_load_dotenv_reads_env_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """_load_dotenv picks up a .env file from CWD."""
        env_file = tmp_path / ".env"
        env_file.write_text("BREQY_TEST_VAR_XYZ=hello_from_dotenv\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("BREQY_TEST_VAR_XYZ", raising=False)

        _load_dotenv()
        assert os.getenv("BREQY_TEST_VAR_XYZ") == "hello_from_dotenv"

        # Cleanup
        monkeypatch.delenv("BREQY_TEST_VAR_XYZ", raising=False)

    def test_load_dotenv_does_not_override_existing_vars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Existing env vars take precedence over .env values."""
        env_file = tmp_path / ".env"
        env_file.write_text("BREQY_TEST_OVERRIDE=from_file\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("BREQY_TEST_OVERRIDE", "from_env")

        _load_dotenv()
        assert os.getenv("BREQY_TEST_OVERRIDE") == "from_env"

    def test_load_dotenv_no_file_no_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """_load_dotenv handles missing .env gracefully."""
        monkeypatch.chdir(tmp_path)
        _load_dotenv()  # Should not raise


# ---------------------------------------------------------------------------
# __main__.py
# ---------------------------------------------------------------------------


class TestMainModule:
    """Tests for breqy/__main__.py."""

    def test_main_module_invokes_cli_main(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """python -m breqy invokes cli.main via __main__.py."""
        import runpy

        called: list[bool] = []

        def mock_main(*args: object, **kwargs: object) -> None:
            called.append(True)

        monkeypatch.setattr("breqy.cli.main", mock_main)

        runpy.run_module("breqy", run_name="__main__", alter_sys=False)
        assert called
