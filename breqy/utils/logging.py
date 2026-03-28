"""Structured logging setup using structlog."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


def setup_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
    process: str = "engine",
    agent_id: str = "",
) -> None:
    """Configure structlog with human-readable console output and optional file logging.

    When *log_dir* is ``None`` (the default), behaviour is identical to the
    original implementation: structlog writes human-readable output to stderr.

    When *log_dir* is given the function additionally:
    * creates *log_dir* if it does not exist,
    * opens a file handler that writes JSON-lines to
      ``{log_dir}/agent-{agent_id}.log`` (when *process* is ``"agent"`` and
      *agent_id* is non-empty) or ``{log_dir}/{process}.log`` otherwise,
    * binds ``process`` and ``agent_id`` into structlog context vars so they
      appear in every subsequent log entry.

    Safe to call multiple times — structlog.configure() is idempotent.
    Falls back to INFO for unrecognized level strings.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    if log_dir is None:
        # ---- original stderr-only path (backward compatible) ----
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.dev.set_exc_info,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=False,
        )
        return

    # ---- file-logging path (JSON lines) ----
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Determine log filename
    if process == "agent" and agent_id:
        filename = f"agent-{agent_id}.log"
    else:
        filename = f"{process}.log"

    log_file = log_dir / filename

    # Configure stdlib root logger with a file handler for JSON output
    root_logger = logging.getLogger()
    # Remove any existing handlers to avoid duplicates on repeated calls
    root_logger.handlers.clear()
    root_logger.setLevel(numeric_level)

    file_handler = logging.FileHandler(str(log_file), mode="a", encoding="utf-8")
    file_handler.setLevel(numeric_level)
    root_logger.addHandler(file_handler)

    # Clear previous context vars, then bind process context
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(process=process, agent_id=agent_id)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    # Attach a ProcessorFormatter to the file handler so structlog
    # processors (including JSONRenderer) are applied to every record.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
        ],
    )
    file_handler.setFormatter(formatter)
