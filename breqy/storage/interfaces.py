"""Abstract repository interfaces.

All persistence is behind these interfaces, injected via DI.
Implementations may use SQLite, Postgres, or other backends.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from breqy.domain.enums import (
    ApprovalStatus,
    MemoryPromotionStatus,
    MemoryScope,
    SessionStatus,
    TaskStatus,
    ToolStatus,
)
from breqy.domain.events import Event
from breqy.domain.models import (
    ApprovalDecision,
    ApprovalGrant,
    ApprovalRequest,
    MemoryPromotion,
    MemoryRecord,
    Message,
    Participant,
    Session,
    Task,
    ToolInvocation,
)


class SessionRepository(ABC):
    @abstractmethod
    async def create(self, session: Session) -> None: ...

    @abstractmethod
    async def get(self, session_id: str) -> Session | None: ...

    @abstractmethod
    async def list_active(self) -> list[Session]: ...

    @abstractmethod
    async def update_status(self, session_id: str, status: SessionStatus) -> None: ...

    @abstractmethod
    async def update_timestamp(self, session_id: str) -> None: ...

    @abstractmethod
    async def update_workspace_paths(
        self, session_id: str, paths: list[str]
    ) -> None: ...


class ParticipantRepository(ABC):
    @abstractmethod
    async def create(self, participant: Participant) -> None: ...

    @abstractmethod
    async def get(self, participant_id: str) -> Participant | None: ...

    @abstractmethod
    async def list_by_session(self, session_id: str) -> list[Participant]: ...

    @abstractmethod
    async def get_active_by_session(self, session_id: str) -> list[Participant]: ...

    @abstractmethod
    async def get_by_agent_and_session(
        self, agent_id: str, session_id: str
    ) -> Participant | None: ...

    @abstractmethod
    async def set_left_at(self, participant_id: str, left_at: datetime) -> None: ...


class MessageRepository(ABC):
    @abstractmethod
    async def create(self, message: Message) -> None: ...

    @abstractmethod
    async def list_by_session(
        self, session_id: str, limit: int = 100, before: datetime | None = None
    ) -> list[Message]: ...


class EventRepository(ABC):
    """Append-only event log."""

    @abstractmethod
    async def append(self, event: Event) -> None: ...

    @abstractmethod
    async def list_by_session(
        self, session_id: str, limit: int = 100, after_event_id: str = ""
    ) -> list[Event]: ...


class TaskRepository(ABC):
    @abstractmethod
    async def create(self, task: Task) -> None: ...

    @abstractmethod
    async def get(self, task_id: str) -> Task | None: ...

    @abstractmethod
    async def list_by_session(self, session_id: str) -> list[Task]: ...

    @abstractmethod
    async def update_status(self, task_id: str, status: TaskStatus) -> None: ...


class ApprovalRepository(ABC):
    @abstractmethod
    async def create_request(self, request: ApprovalRequest) -> None: ...

    @abstractmethod
    async def create_decision(self, decision: ApprovalDecision) -> None: ...

    @abstractmethod
    async def get_request(self, request_id: str) -> ApprovalRequest | None: ...

    @abstractmethod
    async def get_pending_by_session(self, session_id: str) -> list[ApprovalRequest]: ...

    @abstractmethod
    async def update_request_status(
        self, request_id: str, status: ApprovalStatus
    ) -> None: ...

    @abstractmethod
    async def get_session_grants(self, session_id: str) -> list[ApprovalDecision]: ...

    @abstractmethod
    async def create_grant(self, grant: ApprovalGrant) -> None: ...

    @abstractmethod
    async def has_grant(self, *, session_id: str, grant_key: str) -> bool: ...

    @abstractmethod
    async def get_grants(self, session_id: str | None = None) -> list[ApprovalGrant]: ...


class ToolInvocationRepository(ABC):
    @abstractmethod
    async def create(self, invocation: ToolInvocation) -> None: ...

    @abstractmethod
    async def get(self, invocation_id: str) -> ToolInvocation | None: ...

    @abstractmethod
    async def list_by_session(self, session_id: str) -> list[ToolInvocation]: ...

    @abstractmethod
    async def update_result(
        self,
        invocation_id: str,
        status: ToolStatus,
        result: dict[str, Any] | None,
        error: str,
        summary: str,
        approval_id: str | None = None,
        *,
        started_at: datetime | None = None,
    ) -> None: ...


class MemoryRepository(ABC):
    @abstractmethod
    async def create_record(self, record: MemoryRecord) -> None: ...

    @abstractmethod
    async def get_record(self, record_id: str) -> MemoryRecord | None: ...

    @abstractmethod
    async def list_records(
        self,
        scope: MemoryScope,
        *,
        session_id: str | None = None,
        agent_id: str | None = None,
        tags: list[str] | None = None,
        task_id: str | None = None,
        approval_id: str | None = None,
        artifact_id: str | None = None,
        linked_event_id: str | None = None,
        promotion_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]: ...

    @abstractmethod
    async def update_record_promotion(
        self,
        record_id: str,
        promotion_id: str | None,
    ) -> None: ...

    @abstractmethod
    async def create_promotion(self, promotion: MemoryPromotion) -> None: ...

    @abstractmethod
    async def get_promotion(self, promotion_id: str) -> MemoryPromotion | None: ...

    @abstractmethod
    async def update_promotion_state(
        self,
        promotion_id: str,
        status: MemoryPromotionStatus,
        target_record_id: str | None = None,
    ) -> None: ...
