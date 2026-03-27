"""Typed A2A event schemas for the Breqy system.

All events exchanged between engine, agents, and TUI use one of these
typed classes. Import from ``breqy.domain.events`` — never construct
raw dicts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator

from breqy.domain.enums import (
    ApprovalStatus,
    EventType,
    MemoryPromotionStatus,
    MemoryRecordKind,
    MemoryScope,
    MessageRole,
    TaskStatus,
    ToolStatus,
)
from breqy.domain.ids import generate_prefixed_id
from breqy.domain.models import (
    SessionContextBundle,
    StructuredErrorPayload,
    StructuredResultPayload,
    TaskContextReference,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel):
    """Base class for all A2A events."""

    event_id: str = Field(default_factory=lambda: generate_prefixed_id("evt"))
    event_type: EventType
    schema_version: int = 1
    session_id: str
    agent_id: str = ""
    correlation_id: str = ""
    timestamp: datetime = Field(default_factory=_now)


class FixedEventTypeEvent(Event):
    @classmethod
    def expected_event_types(cls) -> tuple[EventType, ...]:
        value = cls.model_fields["event_type"].default
        return (value,)

    @model_validator(mode="after")
    def validate_fixed_event_type(self) -> FixedEventTypeEvent:
        if self.event_type not in self.expected_event_types():
            expected = ", ".join(event_type.value for event_type in self.expected_event_types())
            raise ValueError(f"{type(self).__name__} requires event_type to be one of: {expected}")
        return self


class CorrelatedAgentEvent(Event):
    @model_validator(mode="after")
    def validate_required_agent_fields(self) -> CorrelatedAgentEvent:
        if not self.agent_id:
            raise ValueError("correlated agent events require agent_id")
        if not self.correlation_id:
            raise ValueError("correlated agent events require correlation_id")
        return self


# --------------------------------------------------------------------------- #
# Session events
# --------------------------------------------------------------------------- #


class SessionCreatedEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.SESSION_CREATED
    primary_agent_id: str = ""
    workspace: str = ""


class SessionResumedEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.SESSION_RESUMED


class SessionClosedEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.SESSION_CLOSED


# --------------------------------------------------------------------------- #
# Message events
# --------------------------------------------------------------------------- #


class MessageSentEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.MESSAGE_SENT
    message_id: str
    role: MessageRole
    content: str


class MessageChunkEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.MESSAGE_CHUNK
    message_id: str
    chunk: str
    chunk_index: int = 0


class AgentWorkRequestedEvent(CorrelatedAgentEvent, FixedEventTypeEvent):
    event_type: EventType = EventType.AGENT_WORK_REQUESTED
    message_id: str
    user_message_content: str
    session_context: SessionContextBundle
    task_context: TaskContextReference | None = None
    active_skill_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_task_context_agreement(self) -> AgentWorkRequestedEvent:
        if self.task_context is None or self.session_context.task_context is None:
            return self
        if self.task_context != self.session_context.task_context:
            raise ValueError("event task_context must match session_context.task_context when both are present")
        return self


# --------------------------------------------------------------------------- #
# Task events
# --------------------------------------------------------------------------- #


class TaskUpdatedEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.TASK_UPDATED
    task_id: str
    title: str = ""
    status: TaskStatus = TaskStatus.PENDING

    @classmethod
    def expected_event_types(cls) -> tuple[EventType, ...]:
        return (
            EventType.TASK_CREATED,
            EventType.TASK_UPDATED,
            EventType.TASK_COMPLETED,
        )


class ToolExecutionRequestedEvent(CorrelatedAgentEvent, FixedEventTypeEvent):
    event_type: EventType = EventType.TOOL_EXECUTION_REQUESTED
    invocation_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_correlation_matches_invocation(self) -> ToolExecutionRequestedEvent:
        if self.correlation_id != self.invocation_id:
            raise ValueError("tool execution request requires correlation_id to match invocation_id")
        return self


class ToolExecutionResultEvent(CorrelatedAgentEvent, FixedEventTypeEvent):
    event_type: EventType = EventType.TOOL_EXECUTION_RESULT
    invocation_id: str
    success_payload: StructuredResultPayload | None = None
    failure_payload: StructuredErrorPayload | None = None

    @model_validator(mode="after")
    def validate_single_outcome(self) -> ToolExecutionResultEvent:
        if (self.success_payload is None) == (self.failure_payload is None):
            raise ValueError("tool execution result requires exactly one outcome payload")
        if self.correlation_id != self.invocation_id:
            raise ValueError("tool execution result requires correlation_id to match invocation_id")
        return self


# --------------------------------------------------------------------------- #
# Tool events
# --------------------------------------------------------------------------- #


class ToolInvocationStartedEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.TOOL_INVOCATION_STARTED
    invocation_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class ToolInvocationCompletedEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.TOOL_INVOCATION_COMPLETED
    invocation_id: str
    tool_name: str
    status: ToolStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    summary: str = ""


class ToolInvocationFailedEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.TOOL_INVOCATION_FAILED
    invocation_id: str
    tool_name: str
    error: str = ""


class ToolOutputChunkEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.TOOL_OUTPUT_CHUNK
    invocation_id: str
    chunk: str
    chunk_index: int = 0


class PrivateMemoryOperationRequestedEvent(CorrelatedAgentEvent, FixedEventTypeEvent):
    event_type: EventType = EventType.PRIVATE_MEMORY_OPERATION_REQUESTED
    invocation_id: str
    operation_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_correlation_matches_invocation(self) -> PrivateMemoryOperationRequestedEvent:
        if self.correlation_id != self.invocation_id:
            raise ValueError("private memory request requires correlation_id to match invocation_id")
        return self


class PrivateMemoryOperationResultEvent(CorrelatedAgentEvent, FixedEventTypeEvent):
    event_type: EventType = EventType.PRIVATE_MEMORY_OPERATION_RESULT
    invocation_id: str
    operation_name: str
    success_payload: StructuredResultPayload | None = None
    failure_payload: StructuredErrorPayload | None = None

    @model_validator(mode="after")
    def validate_single_outcome(self) -> PrivateMemoryOperationResultEvent:
        if (self.success_payload is None) == (self.failure_payload is None):
            raise ValueError("private memory result requires exactly one outcome payload")
        if self.correlation_id != self.invocation_id:
            raise ValueError("private memory result requires correlation_id to match invocation_id")
        return self


# --------------------------------------------------------------------------- #
# Approval events
# --------------------------------------------------------------------------- #


class ApprovalRequestedEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.APPROVAL_REQUESTED
    approval_id: str
    invocation_id: str
    description: str


class ApprovalDecidedEvent(FixedEventTypeEvent):
    """event_type can be APPROVAL_GRANTED or APPROVAL_DENIED."""

    event_type: EventType = EventType.APPROVAL_GRANTED
    approval_id: str
    decision: ApprovalStatus = ApprovalStatus.GRANTED

    @classmethod
    def expected_event_types(cls) -> tuple[EventType, ...]:
        return (EventType.APPROVAL_GRANTED, EventType.APPROVAL_DENIED)

    @model_validator(mode="after")
    def validate_event_type_matches_decision(self) -> ApprovalDecidedEvent:
        if self.event_type == EventType.APPROVAL_GRANTED and self.decision != ApprovalStatus.GRANTED:
            raise ValueError("approval.granted events must use granted decision")
        if self.event_type == EventType.APPROVAL_DENIED and self.decision != ApprovalStatus.DENIED:
            raise ValueError("approval.denied events must use denied decision")
        return self


# --------------------------------------------------------------------------- #
# Agent lifecycle events
# --------------------------------------------------------------------------- #


class AgentLifecycleEvent(FixedEventTypeEvent):
    """event_type can be AGENT_CONNECTED or AGENT_DISCONNECTED."""

    event_type: EventType = EventType.AGENT_CONNECTED
    # agent_id inherited from Event; agents must always supply this

    @classmethod
    def expected_event_types(cls) -> tuple[EventType, ...]:
        return (EventType.AGENT_CONNECTED, EventType.AGENT_DISCONNECTED)

    @model_validator(mode="after")
    def validate_agent_id_present(self) -> AgentLifecycleEvent:
        if not self.agent_id:
            raise ValueError("agent lifecycle events require agent_id")
        return self


# --------------------------------------------------------------------------- #
# Control events
# --------------------------------------------------------------------------- #


class ControlEvent(FixedEventTypeEvent):
    """event_type can be CONTROL_STOP, CONTROL_STEER, CONTROL_STOP_AND_STEER, or CONTROL_CIRCUIT_BREAK."""

    event_type: EventType = EventType.CONTROL_STOP
    new_direction: str = ""

    @classmethod
    def expected_event_types(cls) -> tuple[EventType, ...]:
        return (
            EventType.CONTROL_STOP,
            EventType.CONTROL_STOP_AND_STEER,
            EventType.CONTROL_STEER,
            EventType.CONTROL_CIRCUIT_BREAK,
        )


# --------------------------------------------------------------------------- #
# Memory events
# --------------------------------------------------------------------------- #


class MemoryRecordEvent(Event):
    record_id: str
    scope: MemoryScope
    kind: MemoryRecordKind
    source: str
    content: str
    task_id: str | None = None
    approval_id: str | None = None
    artifact_id: str | None = None
    linked_event_id: str | None = None
    promotion_id: str | None = None


class MemoryRecordCreatedEvent(MemoryRecordEvent, FixedEventTypeEvent):
    event_type: EventType = EventType.MEMORY_RECORD_CREATED


class MemoryRecordUpdatedEvent(MemoryRecordEvent, FixedEventTypeEvent):
    event_type: EventType = EventType.MEMORY_RECORD_UPDATED


class MemoryPromotionRequestedEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.MEMORY_PROMOTION_REQUESTED
    promotion_id: str
    source_record_id: str
    approval_id: str | None = None
    status: MemoryPromotionStatus = MemoryPromotionStatus.PENDING

    @model_validator(mode="after")
    def validate_requested_status(self) -> MemoryPromotionRequestedEvent:
        if self.event_type != EventType.MEMORY_PROMOTION_REQUESTED:
            raise ValueError("requested memory promotion events must use memory.promotion.requested")
        if self.status != MemoryPromotionStatus.PENDING:
            raise ValueError("requested memory promotion events must use pending status")
        return self


class MemoryPromotionApprovedEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.MEMORY_PROMOTION_APPROVED
    promotion_id: str
    source_record_id: str
    target_record_id: str
    approval_id: str | None = None
    status: MemoryPromotionStatus = MemoryPromotionStatus.APPROVED

    @model_validator(mode="after")
    def validate_approved_status(self) -> MemoryPromotionApprovedEvent:
        if self.event_type != EventType.MEMORY_PROMOTION_APPROVED:
            raise ValueError("approved memory promotion events must use memory.promotion.approved")
        if self.status != MemoryPromotionStatus.APPROVED:
            raise ValueError("approved memory promotion events must use approved status")
        return self


class MemoryPromotionDeniedEvent(FixedEventTypeEvent):
    event_type: EventType = EventType.MEMORY_PROMOTION_DENIED
    promotion_id: str
    source_record_id: str
    approval_id: str | None = None
    status: MemoryPromotionStatus = MemoryPromotionStatus.DENIED
    reason: str = ""

    @model_validator(mode="after")
    def validate_denied_status(self) -> MemoryPromotionDeniedEvent:
        if self.event_type != EventType.MEMORY_PROMOTION_DENIED:
            raise ValueError("denied memory promotion events must use memory.promotion.denied")
        if self.status != MemoryPromotionStatus.DENIED:
            raise ValueError("denied memory promotion events must use denied status")
        return self


# --------------------------------------------------------------------------- #
# Registry + deserializer
# --------------------------------------------------------------------------- #

EVENT_TYPE_MAP: dict[EventType, type[Event]] = {
    EventType.SESSION_CREATED: SessionCreatedEvent,
    EventType.SESSION_RESUMED: SessionResumedEvent,
    EventType.SESSION_CLOSED: SessionClosedEvent,
    EventType.MESSAGE_SENT: MessageSentEvent,
    EventType.MESSAGE_CHUNK: MessageChunkEvent,
    EventType.AGENT_WORK_REQUESTED: AgentWorkRequestedEvent,
    EventType.TASK_CREATED: TaskUpdatedEvent,
    EventType.TASK_UPDATED: TaskUpdatedEvent,
    EventType.TASK_COMPLETED: TaskUpdatedEvent,
    EventType.TOOL_EXECUTION_REQUESTED: ToolExecutionRequestedEvent,
    EventType.TOOL_EXECUTION_RESULT: ToolExecutionResultEvent,
    EventType.TOOL_INVOCATION_STARTED: ToolInvocationStartedEvent,
    EventType.TOOL_INVOCATION_COMPLETED: ToolInvocationCompletedEvent,
    EventType.TOOL_INVOCATION_FAILED: ToolInvocationFailedEvent,
    EventType.TOOL_OUTPUT_CHUNK: ToolOutputChunkEvent,
    EventType.APPROVAL_REQUESTED: ApprovalRequestedEvent,
    EventType.APPROVAL_GRANTED: ApprovalDecidedEvent,
    EventType.APPROVAL_DENIED: ApprovalDecidedEvent,
    EventType.AGENT_CONNECTED: AgentLifecycleEvent,
    EventType.AGENT_DISCONNECTED: AgentLifecycleEvent,
    EventType.CONTROL_STOP: ControlEvent,
    EventType.CONTROL_STOP_AND_STEER: ControlEvent,
    EventType.CONTROL_STEER: ControlEvent,
    EventType.CONTROL_CIRCUIT_BREAK: ControlEvent,
    EventType.PRIVATE_MEMORY_OPERATION_REQUESTED: PrivateMemoryOperationRequestedEvent,
    EventType.PRIVATE_MEMORY_OPERATION_RESULT: PrivateMemoryOperationResultEvent,
    EventType.MEMORY_RECORD_CREATED: MemoryRecordCreatedEvent,
    EventType.MEMORY_RECORD_UPDATED: MemoryRecordUpdatedEvent,
    EventType.MEMORY_PROMOTION_REQUESTED: MemoryPromotionRequestedEvent,
    EventType.MEMORY_PROMOTION_APPROVED: MemoryPromotionApprovedEvent,
    EventType.MEMORY_PROMOTION_DENIED: MemoryPromotionDeniedEvent,
}


def deserialize_event(data: dict[str, Any]) -> Event:
    """Deserialize a dict into the correct typed event subclass.

    Falls back to base ``Event`` for unknown event types.
    """
    try:
        event_type = EventType(data.get("event_type", ""))
        cls = EVENT_TYPE_MAP.get(event_type, Event)
    except ValueError:
        cls = Event
    return cls.model_validate(data)
