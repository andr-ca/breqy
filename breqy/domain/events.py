"""Typed A2A event schemas for the Breqy system.

All events exchanged between engine, agents, and TUI use one of these
typed classes. Import from ``breqy.domain.events`` — never construct
raw dicts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from breqy.domain.enums import (
    ApprovalStatus,
    EventType,
    MessageRole,
    ToolStatus,
)
from breqy.domain.ids import generate_prefixed_id


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


# --------------------------------------------------------------------------- #
# Session events
# --------------------------------------------------------------------------- #


class SessionCreatedEvent(Event):
    event_type: EventType = EventType.SESSION_CREATED
    primary_agent_id: str = ""
    workspace: str = ""


class SessionResumedEvent(Event):
    event_type: EventType = EventType.SESSION_RESUMED


class SessionClosedEvent(Event):
    event_type: EventType = EventType.SESSION_CLOSED


# --------------------------------------------------------------------------- #
# Message events
# --------------------------------------------------------------------------- #


class MessageSentEvent(Event):
    event_type: EventType = EventType.MESSAGE_SENT
    message_id: str
    role: MessageRole
    content: str


class MessageChunkEvent(Event):
    event_type: EventType = EventType.MESSAGE_CHUNK
    message_id: str
    chunk: str
    chunk_index: int = 0


# --------------------------------------------------------------------------- #
# Task events
# --------------------------------------------------------------------------- #


class TaskUpdatedEvent(Event):
    event_type: EventType = EventType.TASK_UPDATED
    task_id: str
    title: str = ""
    status: str = ""


# --------------------------------------------------------------------------- #
# Tool events
# --------------------------------------------------------------------------- #


class ToolInvocationStartedEvent(Event):
    event_type: EventType = EventType.TOOL_INVOCATION_STARTED
    invocation_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class ToolInvocationCompletedEvent(Event):
    event_type: EventType = EventType.TOOL_INVOCATION_COMPLETED
    invocation_id: str
    tool_name: str
    status: ToolStatus
    result: str | None = None
    error: str | None = None
    summary: str = ""


class ToolInvocationFailedEvent(Event):
    event_type: EventType = EventType.TOOL_INVOCATION_FAILED
    invocation_id: str
    tool_name: str
    error: str = ""


class ToolOutputChunkEvent(Event):
    event_type: EventType = EventType.TOOL_OUTPUT_CHUNK
    invocation_id: str
    chunk: str
    chunk_index: int = 0


# --------------------------------------------------------------------------- #
# Approval events
# --------------------------------------------------------------------------- #


class ApprovalRequestedEvent(Event):
    event_type: EventType = EventType.APPROVAL_REQUESTED
    approval_id: str
    invocation_id: str
    description: str


class ApprovalDecidedEvent(Event):
    """event_type can be APPROVAL_GRANTED or APPROVAL_DENIED."""

    event_type: EventType = EventType.APPROVAL_GRANTED
    approval_id: str
    decision: ApprovalStatus = ApprovalStatus.GRANTED


# --------------------------------------------------------------------------- #
# Agent lifecycle events
# --------------------------------------------------------------------------- #


class AgentLifecycleEvent(Event):
    """event_type can be AGENT_CONNECTED or AGENT_DISCONNECTED."""

    event_type: EventType = EventType.AGENT_CONNECTED
    # agent_id inherited from Event; agents must always supply this


# --------------------------------------------------------------------------- #
# Control events
# --------------------------------------------------------------------------- #


class ControlEvent(Event):
    """event_type can be CONTROL_STOP, CONTROL_STEER, CONTROL_STOP_AND_STEER, or CONTROL_CIRCUIT_BREAK."""

    event_type: EventType = EventType.CONTROL_STOP
    new_direction: str = ""


# --------------------------------------------------------------------------- #
# Registry + deserializer
# --------------------------------------------------------------------------- #

EVENT_TYPE_MAP: dict[EventType, type[Event]] = {
    EventType.SESSION_CREATED: SessionCreatedEvent,
    EventType.SESSION_RESUMED: SessionResumedEvent,
    EventType.SESSION_CLOSED: SessionClosedEvent,
    EventType.MESSAGE_SENT: MessageSentEvent,
    EventType.MESSAGE_CHUNK: MessageChunkEvent,
    EventType.TASK_CREATED: TaskUpdatedEvent,
    EventType.TASK_UPDATED: TaskUpdatedEvent,
    EventType.TASK_COMPLETED: TaskUpdatedEvent,
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
