"""Pydantic v2 domain models for the Breqy system."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from breqy.domain.enums import (
    ApprovalStatus,
    AutonomyLevel,
    FilesystemOperation,
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


class Session(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("ses"))
    status: SessionStatus = SessionStatus.ACTIVE
    primary_agent_id: str
    workspace: str = ""
    autonomy_level: AutonomyLevel = AutonomyLevel.SUPERVISED
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Participant(BaseModel):
    id: str = Field(default_factory=lambda: generate_prefixed_id("par"))
    session_id: str
    agent_id: str
    joined_at: datetime = Field(default_factory=_now)


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
    result: str | None = None
    error: str | None = None
    summary: str = ""
    created_at: datetime = Field(default_factory=_now)
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
    session_id: str
    decision: ApprovalStatus
    decided_by: str = "user"
    scope: str = "once"
    created_at: datetime = Field(default_factory=_now)


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
