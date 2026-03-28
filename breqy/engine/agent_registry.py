"""Tracks connected agents and their A2A client IDs."""
from __future__ import annotations

from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AgentInfo:
    """Connection metadata for a registered agent."""
    agent_id: str
    client_id: str
    pid: int | None = None
    session_id: str = ""


class AgentRegistry:
    """Registry of currently connected agents."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}

    def register(
        self, agent_id: str, client_id: str, pid: int | None = None,
        session_id: str = "",
    ) -> None:
        """Register an agent connection."""
        self._agents[agent_id] = AgentInfo(
            agent_id=agent_id, client_id=client_id, pid=pid,
            session_id=session_id,
        )
        logger.info(
            "Agent registered",
            agent_id=agent_id,
            client_id=client_id,
            session_id=session_id,
        )

    def unregister(self, agent_id: str) -> None:
        """Remove an agent (called on disconnect)."""
        self._agents.pop(agent_id, None)
        logger.info("Agent unregistered", agent_id=agent_id)

    def unregister_by_client_id(self, client_id: str) -> None:
        """Remove the agent currently bound to a client ID."""
        info = self.get_by_client_id(client_id)
        if info is not None:
            self.unregister(info.agent_id)

    def get(self, agent_id: str) -> AgentInfo | None:
        """Return agent info by agent_id, or None."""
        return self._agents.get(agent_id)

    def get_by_client_id(self, client_id: str) -> AgentInfo | None:
        """Return agent info by A2A client_id, or None."""
        for info in self._agents.values():
            if info.client_id == client_id:
                return info
        return None

    def list_agents(self) -> list[AgentInfo]:
        """Return all currently registered agents."""
        return list(self._agents.values())

    def list_by_session(self, session_id: str) -> list[AgentInfo]:
        """Return all agents registered to a specific session."""
        return [
            info for info in self._agents.values()
            if info.session_id == session_id
        ]

    def get_by_session_and_agent(
        self, session_id: str, agent_id: str,
    ) -> AgentInfo | None:
        """Return agent info if it belongs to the given session, else None."""
        info = self._agents.get(agent_id)
        if info is not None and info.session_id == session_id:
            return info
        return None
