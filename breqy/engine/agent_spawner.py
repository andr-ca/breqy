"""Agent subprocess spawner and supervisor."""
from __future__ import annotations

import signal
import subprocess
import sys
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SpawnedAgent:
    """Tracks a spawned agent process."""
    agent_dir: str
    process: subprocess.Popen[bytes]
    session_id: str = ""


class AgentSpawner:
    """Spawns and terminates agent subprocesses."""

    def __init__(self, engine_socket: str) -> None:
        self._engine_socket = engine_socket
        self._processes: dict[str, SpawnedAgent] = {}

    def spawn(self, agent_dir: str, *, session_id: str = "") -> int:
        """Spawn an agent process. Returns PID."""
        cmd = self._build_command(agent_dir)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._processes[agent_dir] = SpawnedAgent(
            agent_dir=agent_dir, process=process, session_id=session_id
        )
        logger.info(
            "Agent spawned",
            agent_dir=agent_dir,
            pid=process.pid,
            session_id=session_id,
        )
        return process.pid

    def kill(self, agent_dir: str) -> None:
        """Terminate an agent process (SIGTERM)."""
        spawned = self._processes.pop(agent_dir, None)
        if spawned and spawned.process.poll() is None:
            spawned.process.terminate()
            logger.info("Agent terminated", agent_dir=agent_dir)

    def kill_all(self) -> None:
        """Terminate all running agent processes (SIGTERM)."""
        for agent_dir in list(self._processes.keys()):
            self.kill(agent_dir)

    def force_kill(self, agent_dir: str) -> None:
        """Force-kill an agent process (SIGKILL) for circuit-break."""
        spawned = self._processes.pop(agent_dir, None)
        if spawned and spawned.process.poll() is None:
            spawned.process.send_signal(signal.SIGKILL)
            logger.info("Agent force-killed", agent_dir=agent_dir)

    def force_kill_all(self) -> None:
        """Force-kill all running agent processes (SIGKILL)."""
        for agent_dir in list(self._processes.keys()):
            self.force_kill(agent_dir)

    def kill_by_session(self, session_id: str) -> None:
        """Gracefully terminate all agents for a specific session (SIGTERM)."""
        dirs = [
            d for d, s in self._processes.items()
            if s.session_id == session_id
        ]
        for agent_dir in dirs:
            self.kill(agent_dir)

    def force_kill_by_session(self, session_id: str) -> None:
        """Force-kill all agents for a specific session (SIGKILL)."""
        dirs = [
            d for d, s in self._processes.items()
            if s.session_id == session_id
        ]
        for agent_dir in dirs:
            self.force_kill(agent_dir)

    def list_by_session(self, session_id: str) -> list[SpawnedAgent]:
        """Return all spawned agents for a specific session."""
        return [
            s for s in self._processes.values()
            if s.session_id == session_id
        ]

    def is_running(self, agent_dir: str) -> bool:
        """Return True if the agent process is still alive."""
        spawned = self._processes.get(agent_dir)
        if spawned is None:
            return False
        return spawned.process.poll() is None

    def list_running(self) -> list[str]:
        """Return dirs of all currently-running agents."""
        return [d for d in self._processes if self.is_running(d)]

    def _build_command(self, agent_dir: str) -> list[str]:
        return [
            sys.executable, "-m", "breqy.agents.runtime",
            "--agent-dir", agent_dir,
            "--engine-socket", self._engine_socket,
        ]
