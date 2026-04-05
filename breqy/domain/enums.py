"""Domain enumerations for the Breqy system."""
from __future__ import annotations

from enum import StrEnum


class SessionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    SUSPENDED = "suspended"
    CIRCUIT_BROKEN = "circuit_broken"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(StrEnum):
    SESSION_CREATE_REQUESTED = "session.create_requested"
    SESSION_CREATED = "session.created"
    SESSION_RESUMED = "session.resumed"
    SESSION_CLOSED = "session.closed"
    MESSAGE_SENT = "message.sent"
    MESSAGE_CHUNK = "message.chunk"
    AGENT_WORK_REQUESTED = "agent.work.requested"
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_COMPLETED = "task.completed"
    TOOL_EXECUTION_REQUESTED = "tool.execution.requested"
    TOOL_EXECUTION_RESULT = "tool.execution.result"
    TOOL_INVOCATION_STARTED = "tool.invocation.started"
    TOOL_INVOCATION_COMPLETED = "tool.invocation.completed"
    TOOL_INVOCATION_FAILED = "tool.invocation.failed"
    TOOL_OUTPUT_CHUNK = "tool.output.chunk"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"
    AGENT_CONNECTED = "agent.connected"
    AGENT_DISCONNECTED = "agent.disconnected"
    CONTROL_STOP = "control.stop"
    CONTROL_STOP_AND_STEER = "control.stop_and_steer"
    CONTROL_STEER = "control.steer"
    CONTROL_CIRCUIT_BREAK = "control.circuit_break"
    PRIVATE_MEMORY_OPERATION_REQUESTED = "private_memory.operation.requested"
    PRIVATE_MEMORY_OPERATION_RESULT = "private_memory.operation.result"
    MEMORY_RECORD_CREATED = "memory.record.created"
    MEMORY_RECORD_UPDATED = "memory.record.updated"
    MEMORY_PROMOTION_REQUESTED = "memory.promotion.requested"
    MEMORY_PROMOTION_APPROVED = "memory.promotion.approved"
    MEMORY_PROMOTION_DENIED = "memory.promotion.denied"
    MODEL_INFO = "model.info"
    MODEL_LIST_REQUESTED = "model.list.requested"
    MODEL_LIST_RESPONSE = "model.list.response"
    MODEL_SWITCH_REQUESTED = "model.switch.requested"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ToolStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    EXPIRED = "expired"


class ApprovalGrantScope(StrEnum):
    ONCE = "once"
    SESSION = "session"
    FOREVER = "forever"


class PolicyScope(StrEnum):
    GLOBAL = "global"
    SESSION = "session"
    AGENT = "agent"


class PolicyAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class FilesystemOperation(StrEnum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    LIST = "list"


class AutonomyLevel(StrEnum):
    SUPERVISED = "supervised"
    SEMI_AUTONOMOUS = "semi_autonomous"
    AUTONOMOUS = "autonomous"


class MemoryScope(StrEnum):
    SESSION = "session"
    GLOBAL = "global"


class MemoryRecordKind(StrEnum):
    NOTE = "note"
    FACT = "fact"
    SUMMARY = "summary"
    LESSON = "lesson"


class MemoryPromotionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class CredentialKind(StrEnum):
    ACCESS_TOKEN = "access_token"
    API_KEY = "api_key"


class AuthFlowKind(StrEnum):
    DEVICE = "device"
    PKCE_CODE = "pkce_code"
    API_KEY = "api_key"


class AuthSessionStatus(StrEnum):
    UNAUTHENTICATED = "unauthenticated"
    IN_PROGRESS = "in_progress"
    AUTHENTICATED = "authenticated"
    FAILED = "failed"
