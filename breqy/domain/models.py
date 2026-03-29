"""Pydantic v2 domain models for the Breqy system."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator

from breqy.domain.enums import (
    ApprovalStatus,
    AutonomyLevel,
    FilesystemOperation,
    MemoryPromotionStatus,
    MemoryRecordKind,
    MemoryScope,
    MessageRole,
    PolicyAction,
    PolicyScope,
    SessionStatus,
    TaskStatus,
    ToolStatus,
)
from breqy.domain.ids import generate_prefixed_id


def _now() -> datetime:
    """Return current UTC-aware datetime."""
    return datetime.now(timezone.utc)


class StructuredResultPayload(BaseModel):
    summary: str = ""
    content: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StructuredErrorPayload(BaseModel):
    code: str = ""
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


class TaskContextReference(BaseModel):
    task_id: str
    title: str
    status: TaskStatus
    summary: str = ""
    parent_task_id: str | None = None


class SessionContextBundle(BaseModel):
    messages: list["Message"] = Field(default_factory=list)
    memory_summary: str = ""
    memory_checkpoint: str = ""
    task_context: TaskContextReference | None = None


class Session(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("ses"))
    status: SessionStatus = SessionStatus.ACTIVE
    primary_agent_id: str
    workspace_paths: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Participant(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("par"))
    session_id: str
    agent_id: str
    joined_at: datetime = Field(default_factory=_now)
    left_at: datetime | None = None


class Message(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("msg"))
    session_id: str
    role: MessageRole
    content: str
    agent_id: str | None = None
    created_at: datetime = Field(default_factory=_now)


class Task(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("tsk"))
    session_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    parent_id: str | None = None
    agent_id: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ToolInvocation(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("inv"))
    session_id: str
    agent_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: ToolStatus = ToolStatus.PENDING
    approval_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    summary: str = ""
    started_at: datetime = Field(default_factory=_now)
    completed_at: datetime | None = None


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("apr"))
    session_id: str
    agent_id: str
    tool_invocation_id: str
    description: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=_now)
    expires_at: datetime | None = None


class ApprovalDecision(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("apd"))
    request_id: str
    granted: bool
    extend_to_session: bool = False
    reason: str = ""
    decided_at: datetime = Field(default_factory=_now)


class PolicyRule(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("pol"))
    scope: PolicyScope
    scope_id: str | None = None
    action: PolicyAction
    resource: str
    operations: list[FilesystemOperation] = Field(default_factory=list)
    path_pattern: str | None = None
    created_at: datetime = Field(default_factory=_now)


class FilesystemPolicy(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("fsp"))
    session_id: str | None = None
    path_pattern: str
    allowed_operations: list[FilesystemOperation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


class Agent(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("agt"))
    name: str
    session_id: str | None = None
    model: str = ""
    provider: str = ""
    autonomy_level: AutonomyLevel = AutonomyLevel.SUPERVISED
    created_at: datetime = Field(default_factory=_now)


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("mem"))
    scope: MemoryScope
    session_id: str | None = None
    agent_id: str
    kind: MemoryRecordKind
    source: str
    content: str
    tags: list[str] = Field(default_factory=list)
    task_id: str | None = None
    approval_id: str | None = None
    artifact_id: str | None = None
    linked_event_id: str | None = None
    promotion_id: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def validate_scope_requirements(self) -> MemoryRecord:
        if self.scope == MemoryScope.SESSION and self.session_id is None:
            raise ValueError("session memory records must include session_id")
        if self.scope == MemoryScope.GLOBAL and self.session_id is not None:
            raise ValueError("global memory records must not include session_id")
        return self


class MemoryPromotion(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("mpr"))
    source_record_id: str
    target_record_id: str | None = None
    source_session_id: str
    proposing_agent_id: str
    approval_id: str | None = None
    status: MemoryPromotionStatus = MemoryPromotionStatus.PENDING
    source_scope: MemoryScope = MemoryScope.SESSION
    target_scope: MemoryScope = MemoryScope.GLOBAL
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def validate_supported_promotion_path(self) -> MemoryPromotion:
        if self.source_scope != MemoryScope.SESSION or self.target_scope != MemoryScope.GLOBAL:
            raise ValueError("memory promotion only supports session-to-global")
        if self.status == MemoryPromotionStatus.APPROVED and self.target_record_id is None:
            raise ValueError("approved memory promotions require target_record_id")
        return self


class ModelEntry(BaseModel):
    """A model available from a provider, for model selector UI."""

    provider: str
    model_id: str
    display_name: str
    is_authenticated: bool
