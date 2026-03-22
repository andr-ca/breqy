"""Tests for breqy.domain enums, models, and errors."""
from __future__ import annotations

import pytest


# --------------------------------------------------------------------------- #
# Enum tests
# --------------------------------------------------------------------------- #

def test_session_status_values():
    from breqy.domain.enums import SessionStatus

    assert SessionStatus.ACTIVE == "active"
    assert SessionStatus.CLOSED == "closed"


def test_task_status_values():
    from breqy.domain.enums import TaskStatus

    assert TaskStatus.PENDING == "pending"
    assert TaskStatus.RUNNING == "running"
    assert TaskStatus.COMPLETED == "completed"
    assert TaskStatus.FAILED == "failed"


def test_message_role_values():
    from breqy.domain.enums import MessageRole

    assert MessageRole.USER == "user"
    assert MessageRole.ASSISTANT == "assistant"
    assert MessageRole.SYSTEM == "system"


def test_tool_status_values():
    from breqy.domain.enums import ToolStatus

    assert ToolStatus.PENDING == "pending"
    assert ToolStatus.APPROVED == "approved"
    assert ToolStatus.DENIED == "denied"
    assert ToolStatus.COMPLETED == "completed"
    assert ToolStatus.FAILED == "failed"


def test_approval_status_values():
    from breqy.domain.enums import ApprovalStatus

    assert ApprovalStatus.PENDING == "pending"
    assert ApprovalStatus.GRANTED == "granted"
    assert ApprovalStatus.DENIED == "denied"
    assert ApprovalStatus.EXPIRED == "expired"


def test_autonomy_level_values():
    from breqy.domain.enums import AutonomyLevel

    assert AutonomyLevel.SUPERVISED == "supervised"
    assert AutonomyLevel.SEMI_AUTONOMOUS == "semi_autonomous"
    assert AutonomyLevel.AUTONOMOUS == "autonomous"


# --------------------------------------------------------------------------- #
# Model tests
# --------------------------------------------------------------------------- #

def test_session_defaults():
    from breqy.domain.models import Session
    from breqy.domain.enums import SessionStatus

    s = Session(primary_agent_id="agent_breqy")
    assert s.id is not None
    assert s.id.startswith("ses_")
    assert s.status == SessionStatus.ACTIVE
    assert s.created_at is not None
    assert s.primary_agent_id == "agent_breqy"


def test_session_closed_status():
    from breqy.domain.models import Session
    from breqy.domain.enums import SessionStatus

    s = Session(primary_agent_id="agent_breqy", status=SessionStatus.CLOSED)
    assert s.status == SessionStatus.CLOSED


def test_message_valid():
    from breqy.domain.models import Message
    from breqy.domain.enums import MessageRole

    m = Message(session_id="ses_test", role=MessageRole.USER, content="Hello")
    assert m.id is not None
    assert m.id.startswith("msg_")
    assert m.content == "Hello"


def test_task_no_parent():
    from breqy.domain.models import Task
    from breqy.domain.enums import TaskStatus

    t = Task(session_id="ses_test", title="Install nginx", status=TaskStatus.PENDING)
    assert t.parent_id is None
    assert t.title == "Install nginx"


def test_task_with_parent():
    from breqy.domain.models import Task
    from breqy.domain.enums import TaskStatus

    parent_id = "tsk_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    t = Task(
        session_id="ses_test",
        title="Sub-task",
        status=TaskStatus.PENDING,
        parent_id=parent_id,
    )
    assert t.parent_id == parent_id


def test_tool_invocation_valid():
    from breqy.domain.models import ToolInvocation
    from breqy.domain.enums import ToolStatus

    ti = ToolInvocation(
        session_id="ses_test",
        agent_id="agt_test",
        tool_name="shell",
        arguments={"command": "ls"},
        status=ToolStatus.PENDING,
    )
    assert ti.tool_name == "shell"
    assert ti.arguments == {"command": "ls"}


def test_approval_request_valid():
    from breqy.domain.models import ApprovalRequest
    from breqy.domain.enums import ApprovalStatus

    ar = ApprovalRequest(
        session_id="ses_test",
        agent_id="agt_test",
        tool_invocation_id="inv_test",
        description="Run ls",
        status=ApprovalStatus.PENDING,
    )
    assert ar.status == ApprovalStatus.PENDING
    assert ar.description == "Run ls"


def test_policy_rule_valid():
    from breqy.domain.models import PolicyRule
    from breqy.domain.enums import PolicyScope, PolicyAction

    rule = PolicyRule(
        scope=PolicyScope.GLOBAL,
        action=PolicyAction.DENY,
        resource="tool:shell",
    )
    assert rule.scope == PolicyScope.GLOBAL
    assert rule.resource == "tool:shell"


def test_model_roundtrip():
    from breqy.domain.models import Session

    s = Session(primary_agent_id="agent_breqy")
    dumped = s.model_dump()
    restored = Session.model_validate(dumped)
    assert restored.id == s.id
    assert restored.primary_agent_id == s.primary_agent_id


def test_model_dump_json():
    from breqy.domain.models import Session
    import json

    s = Session(primary_agent_id="agent_breqy")
    json_str = s.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["id"] == s.id


# --------------------------------------------------------------------------- #
# Error hierarchy tests
# --------------------------------------------------------------------------- #

def test_all_errors_are_breqy_error_subclasses():
    from breqy.domain.errors import (
        BreqyError,
        SessionNotFoundError,
        AgentNotFoundError,
        PolicyDeniedError,
        ApprovalRequiredError,
        ToolExecutionError,
        AgentSpawnError,
        TransportError,
    )

    for cls in [
        SessionNotFoundError,
        AgentNotFoundError,
        PolicyDeniedError,
        ApprovalRequiredError,
        ToolExecutionError,
        AgentSpawnError,
        TransportError,
    ]:
        assert issubclass(cls, BreqyError), f"{cls.__name__} must subclass BreqyError"


def test_breqy_error_is_exception():
    from breqy.domain.errors import BreqyError

    assert issubclass(BreqyError, Exception)


def test_policy_denied_error_carries_resource():
    from breqy.domain.errors import PolicyDeniedError

    err = PolicyDeniedError("tool:shell", "not allowed")
    assert err.resource == "tool:shell"
    assert "not allowed" in str(err)


def test_approval_required_error_carries_request_id():
    from breqy.domain.errors import ApprovalRequiredError

    err = ApprovalRequiredError("apr_123")
    assert err.approval_request_id == "apr_123"
