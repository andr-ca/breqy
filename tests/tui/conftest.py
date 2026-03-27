"""Shared fixtures for TUI tests."""
from __future__ import annotations

import pytest

from breqy.domain.enums import (
    ApprovalStatus,
    MessageRole,
    SessionStatus,
    TaskStatus,
    ToolStatus,
)
from breqy.domain.models import (
    ApprovalRequest,
    Message,
    Task,
    ToolInvocation,
)
from breqy.tui.state import SessionState


@pytest.fixture
def session_state() -> SessionState:
    """Return a fresh SessionState for testing."""
    return SessionState(session_id="ses_test123")


@pytest.fixture
def sample_message() -> Message:
    """Return a sample user message."""
    return Message(
        id="msg_001",
        session_id="ses_test123",
        role=MessageRole.USER,
        content="Hello, assistant!",
    )


@pytest.fixture
def sample_assistant_message() -> Message:
    """Return a sample assistant message."""
    return Message(
        id="msg_002",
        session_id="ses_test123",
        role=MessageRole.ASSISTANT,
        content="Hello! How can I help?",
        agent_id="agt_breqy",
    )


@pytest.fixture
def sample_task() -> Task:
    """Return a sample task."""
    return Task(
        id="tsk_001",
        session_id="ses_test123",
        title="Fix the bug",
        description="Fix the null pointer bug",
        status=TaskStatus.PENDING,
        agent_id="agt_breqy",
    )


@pytest.fixture
def sample_tool_invocation() -> ToolInvocation:
    """Return a sample tool invocation."""
    return ToolInvocation(
        id="inv_001",
        session_id="ses_test123",
        agent_id="agt_breqy",
        tool_name="shell",
        arguments={"command": "ls -la"},
        status=ToolStatus.RUNNING,
    )


@pytest.fixture
def sample_approval_request() -> ApprovalRequest:
    """Return a sample approval request."""
    return ApprovalRequest(
        id="apr_001",
        session_id="ses_test123",
        agent_id="agt_breqy",
        tool_invocation_id="inv_001",
        description="Execute shell command: ls -la",
        status=ApprovalStatus.PENDING,
    )
