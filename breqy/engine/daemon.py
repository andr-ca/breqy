"""Engine daemon: lifecycle management, signal handling, entry point."""
from __future__ import annotations

import asyncio
import signal
from pathlib import Path

import structlog

from breqy.config.models import EngineConfig
from breqy.engine.server import EngineServer
from breqy.storage.sqlite.connection import create_connection
from breqy.storage.sqlite.migrations import run_migrations
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.message_repo import SqliteMessageRepository
from breqy.storage.sqlite.event_repo import SqliteEventRepository
from breqy.storage.sqlite.task_repo import SqliteTaskRepository
from breqy.storage.sqlite.approval_repo import SqliteApprovalRepository
from breqy.utils.logging import setup_logging

logger = structlog.get_logger(__name__)


class EngineDaemon:
    """Top-level daemon that owns the engine lifecycle."""

    def __init__(self, config: EngineConfig) -> None:
        self._config = config
        self._server: EngineServer | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def server(self) -> EngineServer | None:
        return self._server

    async def start(self) -> None:
        """Initialize storage, build engine server, and start all components."""
        setup_logging(self._config.log_level)

        # Ensure data directory exists
        Path(self._config.data_dir).mkdir(parents=True, exist_ok=True)

        # Initialize storage layer
        conn = await create_connection(self._config.db_path)
        await run_migrations(conn)

        session_repo = SqliteSessionRepository(conn)
        message_repo = SqliteMessageRepository(conn)
        event_repo = SqliteEventRepository(conn)
        task_repo = SqliteTaskRepository(conn)
        approval_repo = SqliteApprovalRepository(conn)

        self._server = EngineServer(
            socket_path=self._config.socket_path,
            session_repo=session_repo,
            message_repo=message_repo,
            event_repo=event_repo,
            task_repo=task_repo,
            approval_repo=approval_repo,
        )
        await self._server.start()
        self._running = True
        logger.info("Engine daemon started", socket=self._config.socket_path)

    async def stop(self) -> None:
        """Gracefully stop the engine."""
        if self._server:
            await self._server.stop()
        self._running = False
        logger.info("Engine daemon stopped")


def main() -> None:
    """Entry point for breqy-engine command."""
    from breqy.config.loader import load_engine_config

    config = load_engine_config()

    async def run() -> None:
        daemon = EngineDaemon(config)
        loop = asyncio.get_running_loop()

        stop_task: asyncio.Task[None] | None = None

        def handle_signal() -> None:
            nonlocal stop_task
            if stop_task is None:
                stop_task = loop.create_task(daemon.stop())

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_signal)

        await daemon.start()

        while daemon.is_running:
            await asyncio.sleep(1)

    asyncio.run(run())


if __name__ == "__main__":
    main()
