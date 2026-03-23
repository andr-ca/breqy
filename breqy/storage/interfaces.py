"""Abstract repository interfaces.

All persistence is behind these interfaces, injected via DI.
Implementations may use SQLite, Postgres, or other backends.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from breqy.domain.enums import ApprovalStatus, SessionStatus, TaskStatus, ToolStatus
from breqy.domain.events import Event
from breqy.domain.models import (
    ApprovalDecision,
    ApprovalRequest,
    Message,
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
    ) -> None: ...
