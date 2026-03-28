"""Tests for structured logging setup."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

import structlog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_logging() -> None:
    """Reset stdlib root logger and structlog context between tests."""
    root = logging.getLogger()
    for h in list(root.handlers):
        try:
            h.close()
        except Exception:
            pass
    root.handlers.clear()
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()


# ---------------------------------------------------------------------------
# Backward compatibility (no file, no console flag)
# ---------------------------------------------------------------------------

def test_setup_logging_does_not_raise():
    """setup_logging() with valid level runs without error."""
    from breqy.utils.logging import setup_logging

    try:
        setup_logging("INFO")  # must not raise
    finally:
        _reset_logging()


def test_setup_logging_debug_level():
    """setup_logging() accepts DEBUG level."""
    from breqy.utils.logging import setup_logging

    try:
        setup_logging("DEBUG")  # must not raise
    finally:
        _reset_logging()


def test_setup_logging_invalid_level_falls_back():
    """setup_logging() with unknown level falls back to INFO without raising."""
    from breqy.utils.logging import setup_logging

    try:
        setup_logging("BOGUS_LEVEL")  # must not raise
    finally:
        _reset_logging()


def test_setup_logging_no_file_no_console_preserves_stderr():
    """Default call (no log_file, no console flag) writes to stderr."""
    from breqy.utils.logging import setup_logging

    try:
        setup_logging("DEBUG")
        log = structlog.get_logger()
        log.info("stderr-only-test")  # must not raise
    finally:
        _reset_logging()


# ---------------------------------------------------------------------------
# File logging
# ---------------------------------------------------------------------------

def test_setup_logging_file_creates_log_file(tmp_path: Path):
    """When log_file is given, the log file is created."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "engine.log"
    try:
        setup_logging(level="INFO", log_file=log_file)
        log = structlog.get_logger()
        log.info("hello")

        assert log_file.exists(), f"Expected {log_file} to exist"
        content = log_file.read_text().strip()
        assert len(content) > 0
    finally:
        _reset_logging()


def test_setup_logging_file_json_format(tmp_path: Path):
    """Log file entries are valid JSON lines with standard fields."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "test.log"
    try:
        setup_logging(level="INFO", log_file=log_file)
        log = structlog.get_logger()
        log.info("json-test", session_id="ses_42")

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) >= 1
        entry = json.loads(lines[-1])
        assert entry["event"] == "json-test"
        assert entry["session_id"] == "ses_42"
        assert "level" in entry
        assert "timestamp" in entry
    finally:
        _reset_logging()


def test_setup_logging_file_custom_path(tmp_path: Path):
    """Caller can specify any file path, not just a directory."""
    from breqy.utils.logging import setup_logging

    custom = tmp_path / "custom" / "my-agent.jsonl"
    try:
        setup_logging(level="DEBUG", log_file=custom)
        log = structlog.get_logger()
        log.debug("custom-path-test")

        assert custom.exists()
        entry = json.loads(custom.read_text().strip().splitlines()[-1])
        assert entry["event"] == "custom-path-test"
    finally:
        _reset_logging()


def test_setup_logging_file_parent_created(tmp_path: Path):
    """Parent directories of log_file are created automatically."""
    from breqy.utils.logging import setup_logging

    nested = tmp_path / "a" / "b" / "c" / "deep.log"
    try:
        setup_logging(level="INFO", log_file=nested)
        log = structlog.get_logger()
        log.info("deep")

        assert nested.exists()
    finally:
        _reset_logging()


# ---------------------------------------------------------------------------
# File write modes
# ---------------------------------------------------------------------------

def test_setup_logging_file_mode_append(tmp_path: Path):
    """mode='append' appends to existing file content."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "append.log"
    log_file.write_text('{"event":"old"}\n')
    try:
        setup_logging(level="INFO", log_file=log_file, file_mode="append")
        log = structlog.get_logger()
        log.info("new")

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "old"
        assert json.loads(lines[1])["event"] == "new"
    finally:
        _reset_logging()


def test_setup_logging_file_mode_overwrite(tmp_path: Path):
    """mode='overwrite' truncates the file before writing."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "overwrite.log"
    log_file.write_text('{"event":"old"}\n')
    try:
        setup_logging(level="INFO", log_file=log_file, file_mode="overwrite")
        log = structlog.get_logger()
        log.info("new")

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["event"] == "new"
    finally:
        _reset_logging()


def test_setup_logging_file_mode_backup(tmp_path: Path):
    """mode='backup' renames existing file with timestamp, then starts fresh."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "backup.log"
    log_file.write_text('{"event":"old"}\n')
    try:
        setup_logging(level="INFO", log_file=log_file, file_mode="backup")
        log = structlog.get_logger()
        log.info("new")

        # Original content should be in a backup file
        backups = list(tmp_path.glob("backup.log.*"))
        assert len(backups) == 1, f"Expected 1 backup, got {backups}"
        assert json.loads(backups[0].read_text().strip())["event"] == "old"

        # Current file has only new content
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["event"] == "new"
    finally:
        _reset_logging()


def test_setup_logging_file_mode_backup_no_existing(tmp_path: Path):
    """mode='backup' works fine when no existing file to back up."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "fresh.log"
    try:
        setup_logging(level="INFO", log_file=log_file, file_mode="backup")
        log = structlog.get_logger()
        log.info("first")

        assert log_file.exists()
        backups = list(tmp_path.glob("fresh.log.*"))
        assert len(backups) == 0
    finally:
        _reset_logging()


# ---------------------------------------------------------------------------
# Console control
# ---------------------------------------------------------------------------

def test_setup_logging_console_true_with_file(tmp_path: Path):
    """console=True + log_file: both console and file handlers active."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "both.log"
    try:
        setup_logging(level="INFO", log_file=log_file, console=True)
        log = structlog.get_logger()
        log.info("both-test")

        # File should have content
        assert log_file.exists()
        content = log_file.read_text().strip()
        assert len(content) > 0

        # Root logger should have 2 handlers (file + stderr)
        root = logging.getLogger()
        handler_types = [type(h).__name__ for h in root.handlers]
        assert "FileHandler" in handler_types
        assert "StreamHandler" in handler_types
    finally:
        _reset_logging()


def test_setup_logging_console_false_with_file(tmp_path: Path):
    """console=False + log_file: file handler only, no stderr."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "silent.log"
    try:
        setup_logging(level="INFO", log_file=log_file, console=False)

        root = logging.getLogger()
        handler_types = [type(h).__name__ for h in root.handlers]
        assert "FileHandler" in handler_types
        assert "StreamHandler" not in handler_types
    finally:
        _reset_logging()


def test_setup_logging_console_only_no_file():
    """console=True without log_file: stderr only (no file handler)."""
    from breqy.utils.logging import setup_logging

    try:
        setup_logging(level="DEBUG", console=True)
        log = structlog.get_logger()
        log.info("console-only")  # must not raise
    finally:
        _reset_logging()


# ---------------------------------------------------------------------------
# Level filtering
# ---------------------------------------------------------------------------

def test_setup_logging_debug_level_captured(tmp_path: Path):
    """DEBUG messages appear in log file when level=DEBUG."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "debug.log"
    try:
        setup_logging(level="DEBUG", log_file=log_file)
        log = structlog.get_logger()
        log.debug("trace-detail")

        content = log_file.read_text()
        assert "trace-detail" in content
    finally:
        _reset_logging()


def test_setup_logging_debug_filtered_at_info(tmp_path: Path):
    """DEBUG messages do NOT appear when level=INFO."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "info.log"
    try:
        setup_logging(level="INFO", log_file=log_file)
        log = structlog.get_logger()
        log.debug("should-be-filtered")
        log.info("should-appear")

        content = log_file.read_text()
        assert "should-be-filtered" not in content
        assert "should-appear" in content
    finally:
        _reset_logging()


def test_setup_logging_warning_level(tmp_path: Path):
    """Only WARNING+ messages appear when level=WARNING."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "warn.log"
    try:
        setup_logging(level="WARNING", log_file=log_file)
        log = structlog.get_logger()
        log.info("nope")
        log.warning("yes-warn")
        log.error("yes-error")

        content = log_file.read_text()
        assert "nope" not in content
        assert "yes-warn" in content
        assert "yes-error" in content
    finally:
        _reset_logging()


# ---------------------------------------------------------------------------
# Context binding
# ---------------------------------------------------------------------------

def test_setup_logging_binds_context(tmp_path: Path):
    """Bound context (process, agent_id) appears in every log entry."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "ctx.log"
    try:
        setup_logging(
            level="INFO",
            log_file=log_file,
            context={"process": "agent", "agent_id": "breqy"},
        )
        log = structlog.get_logger()
        log.info("ctx-test")

        entry = json.loads(log_file.read_text().strip().splitlines()[-1])
        assert entry["process"] == "agent"
        assert entry["agent_id"] == "breqy"
    finally:
        _reset_logging()


def test_setup_logging_context_optional(tmp_path: Path):
    """When no context dict is given, no extra keys are bound."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "noctx.log"
    try:
        setup_logging(level="INFO", log_file=log_file)
        log = structlog.get_logger()
        log.info("no-ctx")

        entry = json.loads(log_file.read_text().strip().splitlines()[-1])
        assert "process" not in entry
        assert "agent_id" not in entry
    finally:
        _reset_logging()


# ---------------------------------------------------------------------------
# Repeated calls (idempotent)
# ---------------------------------------------------------------------------

def test_setup_logging_repeated_calls_no_handler_duplication(tmp_path: Path):
    """Calling setup_logging multiple times does not duplicate handlers."""
    from breqy.utils.logging import setup_logging

    log_file = tmp_path / "repeat.log"
    try:
        setup_logging(level="INFO", log_file=log_file, console=True)
        setup_logging(level="INFO", log_file=log_file, console=True)

        root = logging.getLogger()
        assert len(root.handlers) == 2  # file + stderr, not 4
    finally:
        _reset_logging()


# ---------------------------------------------------------------------------
# Helper: default_log_file
# ---------------------------------------------------------------------------

def test_default_log_file_engine():
    """default_log_file returns {log_dir}/{process}.log for engine/tui."""
    from breqy.utils.logging import default_log_file

    result = default_log_file(log_dir=Path("/var/log/breqy"), process="engine")
    assert result == Path("/var/log/breqy/engine.log")


def test_default_log_file_tui():
    """default_log_file returns {log_dir}/tui.log for tui process."""
    from breqy.utils.logging import default_log_file

    result = default_log_file(log_dir=Path("/tmp/logs"), process="tui")
    assert result == Path("/tmp/logs/tui.log")


def test_default_log_file_agent():
    """default_log_file returns {log_dir}/agent-{agent_id}.log for agents."""
    from breqy.utils.logging import default_log_file

    result = default_log_file(
        log_dir=Path("/tmp/logs"), process="agent", agent_id="breqy"
    )
    assert result == Path("/tmp/logs/agent-breqy.log")


def test_default_log_file_agent_no_id():
    """default_log_file falls back to agent.log when agent_id is empty."""
    from breqy.utils.logging import default_log_file

    result = default_log_file(log_dir=Path("/tmp/logs"), process="agent")
    assert result == Path("/tmp/logs/agent.log")
