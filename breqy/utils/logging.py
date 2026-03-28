"""Structured logging setup using structlog."""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog


def default_log_file(
    log_dir: Path,
    process: str = "engine",
    agent_id: str = "",
) -> Path:
    """Return the conventional log file path for a given process.

    Naming convention:
    * ``engine`` → ``{log_dir}/engine.log``
    * ``tui``    → ``{log_dir}/tui.log``
    * ``agent``  → ``{log_dir}/agent-{agent_id}.log`` (or ``agent.log`` if
      *agent_id* is empty)
    * anything else → ``{log_dir}/{process}.log``
    """
    if process == "agent" and agent_id:
        return log_dir / f"agent-{agent_id}.log"
    if process == "agent":
        return log_dir / "agent.log"
    return log_dir / f"{process}.log"


def _resolve_file_mode(log_file: Path, file_mode: str) -> str:
    """Handle backup rotation and return the stdlib file-open mode character.

    Returns ``"a"`` for append, ``"w"`` for overwrite/backup (after renaming).
    """
    if file_mode == "append":
        return "a"

    if file_mode == "backup" and log_file.exists():
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup_path = log_file.with_name(f"{log_file.name}.{stamp}")
        log_file.rename(backup_path)
        return "w"

    if file_mode == "overwrite":
        return "w"

    # backup with no existing file — just start fresh
    return "w"


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    file_mode: str = "append",
    console: bool = True,
    context: dict[str, str] | None = None,
) -> None:
    """Configure structlog with optional file logging and console output.

    Parameters
    ----------
    level:
        Logging level name (``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``).
        Unrecognized values fall back to ``INFO``.
    log_file:
        If given, a :class:`~logging.FileHandler` is created that writes
        JSON-lines to this path.  Parent directories are created automatically.
    file_mode:
        How to open the log file — ``"append"`` (default), ``"overwrite"``
        (truncate), or ``"backup"`` (rename existing file with a UTC timestamp
        suffix, then start fresh).
    console:
        When ``True`` (default) a :class:`~logging.StreamHandler` writing to
        *stderr* is added.  Set to ``False`` to suppress console output (useful
        for agent subprocesses that must not pollute stderr).
    context:
        Optional ``dict[str, str]`` of key-value pairs to bind via
        :func:`structlog.contextvars.bind_contextvars`.  Every subsequent log
        entry will include these keys.

    Safe to call multiple times — previous handlers are cleared first to avoid
    duplicates.  Falls back to ``INFO`` for unrecognized *level* strings.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # ------------------------------------------------------------------
    # No log_file and no explicit console=False → original stderr-only path
    # This preserves backward compatibility with the simple call pattern.
    # ------------------------------------------------------------------
    if log_file is None and console:
        # Bind context vars if requested
        structlog.contextvars.clear_contextvars()
        if context:
            structlog.contextvars.bind_contextvars(**context)

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

    # ------------------------------------------------------------------
    # stdlib-backed path (file and/or console via StreamHandler)
    # ------------------------------------------------------------------
    root_logger = logging.getLogger()
    # Clear existing handlers to prevent duplication on repeated calls
    for h in list(root_logger.handlers):
        try:
            h.close()
        except Exception:  # noqa: BLE001
            pass
    root_logger.handlers.clear()
    root_logger.setLevel(numeric_level)

    # Shared ProcessorFormatter for JSON output on the file handler
    json_formatter = structlog.stdlib.ProcessorFormatter(
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

    # ---- File handler ----
    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        open_mode = _resolve_file_mode(log_file, file_mode)
        file_handler = logging.FileHandler(
            str(log_file), mode=open_mode, encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(json_formatter)
        root_logger.addHandler(file_handler)

    # ---- Console (stderr) handler ----
    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(numeric_level)
        console_formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(),
            ],
            foreign_pre_chain=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
            ],
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # ---- Context vars ----
    structlog.contextvars.clear_contextvars()
    if context:
        structlog.contextvars.bind_contextvars(**context)

    # ---- structlog configuration (stdlib bridge) ----
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
