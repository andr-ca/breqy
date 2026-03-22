"""Tracks connected agents and their A2A client IDs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentInfo:
    """Connection metadata for a registered agent."""
    agent_id: str
    client_id: str
    pid: int | None = None


class AgentRegistry:
    """Registry of currently connected agents."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}

    def register(
        self, agent_id: str, client_id: str, pid: int | None = None
    ) -> None:
        """Register an agent connection."""
        self._agents[agent_id] = AgentInfo(
            agent_id=agent_id, client_id=client_id, pid=pid
        )

    def unregister(self, agent_id: str) -> None:
        """Remove an agent (called on disconnect)."""
        self._agents.pop(agent_id, None)

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
