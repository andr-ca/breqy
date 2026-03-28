"""Engine daemon: lifecycle management, signal handling, entry point."""
from __future__ import annotations

import asyncio
import signal
from pathlib import Path
from typing import Any

import structlog

from breqy.config.models import EngineConfig
from breqy.engine.server import EngineServer
from breqy.policy.evaluator import PolicyEvaluator
from breqy.policy.filesystem import FilesystemPolicyChecker
from breqy.storage.sqlite.connection import create_connection
from breqy.storage.sqlite.migrations import run_migrations
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.message_repo import SqliteMessageRepository
from breqy.storage.sqlite.event_repo import SqliteEventRepository
from breqy.storage.sqlite.task_repo import SqliteTaskRepository
from breqy.storage.sqlite.approval_repo import SqliteApprovalRepository
from breqy.storage.sqlite.memory_repo import SqliteMemoryRepository
from breqy.storage.sqlite.participant_repo import SqliteParticipantRepository
from breqy.storage.sqlite.tool_invocation_repo import SqliteToolInvocationRepository
from breqy.utils.logging import setup_logging

logger = structlog.get_logger(__name__)


class EngineDaemon:
    """Top-level daemon that owns the engine lifecycle."""

    def __init__(self, config: EngineConfig) -> None:
        self._config = config
        self._server: EngineServer | None = None
        self._conn: Any | None = None
        self._running = False
        self._stopped_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def server(self) -> EngineServer | None:
        return self._server

    async def wait_until_stopped(self) -> None:
        """Block until the daemon has been stopped.

        Uses an :class:`asyncio.Event` so the caller wakes up immediately
        when :meth:`stop` completes — no polling delay.
        """
        await self._stopped_event.wait()

    async def start(self) -> None:
        """Initialize storage, build engine server, and start all components."""
        setup_logging(self._config.log_level)

        # Ensure data directory exists
        Path(self._config.data_dir).mkdir(parents=True, exist_ok=True)

        # Ensure socket parent directory exists
        Path(self._config.socket_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize storage layer
        conn = await create_connection(self._config.db_path)
        self._conn = conn
        await run_migrations(conn)

        session_repo = SqliteSessionRepository(conn)
        message_repo = SqliteMessageRepository(conn)
        event_repo = SqliteEventRepository(conn)
        task_repo = SqliteTaskRepository(conn)
        approval_repo = SqliteApprovalRepository(conn)
        memory_repo = SqliteMemoryRepository(conn)
        participant_repo = SqliteParticipantRepository(conn)
        tool_invocation_repo = SqliteToolInvocationRepository(conn)

        self._server = EngineServer(
            socket_path=self._config.socket_path,
            session_repo=session_repo,
            message_repo=message_repo,
            event_repo=event_repo,
            task_repo=task_repo,
            approval_repo=approval_repo,
            memory_repo=memory_repo,
            tool_invocation_repo=tool_invocation_repo,
            policy_evaluator=PolicyEvaluator(self._config.policy_rules),
            filesystem_policy_checker=FilesystemPolicyChecker(
                self._config.filesystem_policies
            ),
            participant_repo=participant_repo,
        )
        await self._server.start()
        self._running = True
        logger.info("Engine daemon started", socket=self._config.socket_path)

    async def stop(self) -> None:
        """Gracefully stop the engine."""
        if self._server:
            await self._server.stop()
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
        self._running = False
        self._stopped_event.set()
        logger.info("Engine daemon stopped")

    async def start_default_agent(self) -> int:
        if self._server is None:
            raise RuntimeError("Engine server is not started")
        session = await self._server.session_manager.create_session("breqy")
        return self._server.agent_spawner.spawn("agents/breqy", session_id=session.id)

    async def restore_sessions(self) -> None:
        """Restore active sessions and respawn their primary agents."""
        if self._server is None:
            raise RuntimeError("Engine server is not started")

        sessions = await self._server.session_manager.restore_active_sessions()
        for session in sessions:
            agent_dir = self._agent_dir_for(session.primary_agent_id)
            self._server.agent_spawner.spawn(
                agent_dir, session_id=session.id,
            )
            logger.info(
                "Agent respawned for restored session",
                session_id=session.id,
                agent_id=session.primary_agent_id,
                agent_dir=agent_dir,
            )

    @staticmethod
    def _agent_dir_for(agent_id: str) -> str:
        """Map agent_id to agent directory.

        Convention: agent_id prefix "agt_" maps to "agents/<name>".
        Falls back to "agents/breqy" for the default agent.
        """
        # Strip common prefixes
        name = agent_id
        for prefix in ("agt_", "agent_"):
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        return f"agents/{name}" if name else "agents/breqy"


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

        await daemon.wait_until_stopped()

    asyncio.run(run())


if __name__ == "__main__":
    main()
