"""Agent-private memory contracts and contract-level test doubles."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PrivateMemoryRecord:
    id: str
    owner_agent_id: str
    content: str
    tags: tuple[str, ...] = field(default_factory=tuple)


class AgentPrivateMemoryStore(ABC):
    @abstractmethod
    async def write(self, *, agent_id: str, record: PrivateMemoryRecord) -> str: ...

    @abstractmethod
    async def search(
        self,
        *,
        agent_id: str,
        query: str = "",
        limit: int = 10,
    ) -> list[PrivateMemoryRecord]: ...


class InMemoryAgentPrivateMemoryStore(AgentPrivateMemoryStore):
    def __init__(self) -> None:
        self._records_by_agent: dict[str, list[PrivateMemoryRecord]] = {}

    async def write(self, *, agent_id: str, record: PrivateMemoryRecord) -> str:
        if record.owner_agent_id != agent_id:
            raise ValueError("private memory record owner must match agent_id")

        self._records_by_agent.setdefault(agent_id, []).append(record)
        return record.id

    async def search(
        self,
        *,
        agent_id: str,
        query: str = "",
        limit: int = 10,
    ) -> list[PrivateMemoryRecord]:
        if limit <= 0:
            return []

        normalized_query = query.strip().casefold()
        results: list[PrivateMemoryRecord] = []

        for record in self._records_by_agent.get(agent_id, []):
            if normalized_query and normalized_query not in record.content.casefold():
                continue
            results.append(record)
            if len(results) >= limit:
                break

        return results
