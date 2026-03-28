"""Tests for structured logging setup."""
from __future__ import annotations

import json
from pathlib import Path

import structlog


def test_setup_logging_does_not_raise():
    """setup_logging() with valid level runs without error."""
    from breqy.utils.logging import setup_logging

    setup_logging("INFO")  # must not raise


def test_setup_logging_debug_level():
    """setup_logging() accepts DEBUG level."""
    from breqy.utils.logging import setup_logging

    setup_logging("DEBUG")  # must not raise


def test_setup_logging_invalid_level_falls_back():
    """setup_logging() with unknown level falls back to INFO without raising."""
    from breqy.utils.logging import setup_logging

    setup_logging("BOGUS_LEVEL")  # must not raise


def test_setup_logging_creates_log_file(tmp_path: Path):
    """When log_dir is given, a log file is created at {log_dir}/{process}.log."""
    from breqy.utils.logging import setup_logging

    try:
        setup_logging(log_dir=tmp_path, process="engine")

        log = structlog.get_logger()
        log.info("hello from engine")

        log_file = tmp_path / "engine.log"
        assert log_file.exists(), f"Expected {log_file} to exist"
        content = log_file.read_text().strip()
        assert len(content) > 0, "Log file should not be empty"
    finally:
        structlog.contextvars.clear_contextvars()


def test_setup_logging_agent_log_file(tmp_path: Path):
    """Agent process creates agent-{agent_id}.log."""
    from breqy.utils.logging import setup_logging

    try:
        setup_logging(log_dir=tmp_path, process="agent", agent_id="solver-1")

        log = structlog.get_logger()
        log.info("hello from agent")

        log_file = tmp_path / "agent-solver-1.log"
        assert log_file.exists(), f"Expected {log_file} to exist"
        content = log_file.read_text().strip()
        assert len(content) > 0, "Log file should not be empty"
    finally:
        structlog.contextvars.clear_contextvars()


def test_setup_logging_json_format(tmp_path: Path):
    """Log entries in file are valid JSON lines with correct fields."""
    from breqy.utils.logging import setup_logging

    try:
        setup_logging(log_dir=tmp_path, process="engine")

        log = structlog.get_logger()
        log.info("test-json-format")

        log_file = tmp_path / "engine.log"
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) >= 1, "Expected at least one log line"

        entry = json.loads(lines[-1])
        assert entry["event"] == "test-json-format"
        assert entry["level"] == "info"
        assert "timestamp" in entry
    finally:
        structlog.contextvars.clear_contextvars()


def test_setup_logging_binds_process_context(tmp_path: Path):
    """process and agent_id appear in log entries."""
    from breqy.utils.logging import setup_logging

    try:
        setup_logging(
            log_dir=tmp_path, process="agent", agent_id="planner-7"
        )

        log = structlog.get_logger()
        log.info("context-check")

        log_file = tmp_path / "agent-planner-7.log"
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) >= 1

        entry = json.loads(lines[-1])
        assert entry["process"] == "agent"
        assert entry["agent_id"] == "planner-7"
    finally:
        structlog.contextvars.clear_contextvars()


def test_setup_logging_no_log_dir_preserves_stderr_behavior():
    """When log_dir is not given, existing stderr-only behavior is preserved."""
    from breqy.utils.logging import setup_logging

    try:
        # Should not raise and should not require log_dir
        setup_logging("DEBUG")

        log = structlog.get_logger()
        log.info("stderr-only-test")  # must not raise
    finally:
        structlog.contextvars.clear_contextvars()
