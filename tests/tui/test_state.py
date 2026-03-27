"""Tests for breqy.tui.state — SessionState dataclass."""
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


class TestSessionStateInit:
    """Test SessionState initialization."""

    def test_creates_with_session_id(self) -> None:
        state = SessionState(session_id="ses_abc")
        assert state.session_id == "ses_abc"

    def test_defaults_to_active_status(self) -> None:
        state = SessionState(session_id="ses_abc")
        assert state.status == SessionStatus.ACTIVE

    def test_defaults_to_empty_collections(self) -> None:
        state = SessionState(session_id="ses_abc")
        assert state.messages == []
        assert state.tasks == {}
        assert state.participants == {}
        assert state.pending_approvals == {}
        assert state.active_tools == {}

    def test_each_instance_gets_independent_collections(self) -> None:
        s1 = SessionState(session_id="ses_1")
        s2 = SessionState(session_id="ses_2")
        s1.messages.append(
            Message(id="msg_x", session_id="ses_1", role=MessageRole.USER, content="hi")
        )
        assert len(s2.messages) == 0


class TestSessionStateAddMessage:
    """Test add_message method."""

    def test_adds_message_to_list(
        self, session_state: SessionState, sample_message: Message
    ) -> None:
        session_state.add_message(sample_message)
        assert len(session_state.messages) == 1
        assert session_state.messages[0] is sample_message

    def test_preserves_message_order(
        self, session_state: SessionState, sample_message: Message, sample_assistant_message: Message
    ) -> None:
        session_state.add_message(sample_message)
        session_state.add_message(sample_assistant_message)
        assert len(session_state.messages) == 2
        assert session_state.messages[0].role == MessageRole.USER
        assert session_state.messages[1].role == MessageRole.ASSISTANT


class TestSessionStateUpdateTask:
    """Test update_task method."""

    def test_creates_new_task_entry(self, session_state: SessionState) -> None:
        session_state.update_task(
            task_id="tsk_001",
            title="New task",
            status=TaskStatus.PENDING,
        )
        assert "tsk_001" in session_state.tasks
        assert session_state.tasks["tsk_001"].title == "New task"
        assert session_state.tasks["tsk_001"].status == TaskStatus.PENDING

    def test_updates_existing_task(self, session_state: SessionState) -> None:
        session_state.update_task(
            task_id="tsk_001", title="Original", status=TaskStatus.PENDING
        )
        session_state.update_task(
            task_id="tsk_001", title="Updated", status=TaskStatus.RUNNING
        )
        assert session_state.tasks["tsk_001"].title == "Updated"
        assert session_state.tasks["tsk_001"].status == TaskStatus.RUNNING

    def test_preserves_session_id(self, session_state: SessionState) -> None:
        session_state.update_task(
            task_id="tsk_001", title="task", status=TaskStatus.PENDING
        )
        assert session_state.tasks["tsk_001"].session_id == "ses_test123"


class TestSessionStateAgentStatus:
    """Test set_agent_status method."""

    def test_sets_agent_connected(self, session_state: SessionState) -> None:
        session_state.set_agent_status("agt_breqy", connected=True)
        assert session_state.participants["agt_breqy"] == "connected"

    def test_sets_agent_disconnected(self, session_state: SessionState) -> None:
        session_state.set_agent_status("agt_breqy", connected=False)
        assert session_state.participants["agt_breqy"] == "disconnected"

    def test_updates_existing_agent_status(self, session_state: SessionState) -> None:
        session_state.set_agent_status("agt_breqy", connected=True)
        session_state.set_agent_status("agt_breqy", connected=False)
        assert session_state.participants["agt_breqy"] == "disconnected"


class TestSessionStateApprovals:
    """Test approval management."""

    def test_adds_approval_request(
        self, session_state: SessionState, sample_approval_request: ApprovalRequest
    ) -> None:
        session_state.add_approval(sample_approval_request)
        assert "apr_001" in session_state.pending_approvals
        assert session_state.pending_approvals["apr_001"] is sample_approval_request

    def test_resolves_approval(
        self, session_state: SessionState, sample_approval_request: ApprovalRequest
    ) -> None:
        session_state.add_approval(sample_approval_request)
        session_state.resolve_approval("apr_001")
        assert "apr_001" not in session_state.pending_approvals

    def test_resolve_nonexistent_approval_is_safe(
        self, session_state: SessionState
    ) -> None:
        # Should not raise
        session_state.resolve_approval("apr_nonexistent")


class TestSessionStateTools:
    """Test tool invocation tracking."""

    def test_updates_tool_invocation(
        self, session_state: SessionState, sample_tool_invocation: ToolInvocation
    ) -> None:
        session_state.update_tool(sample_tool_invocation)
        assert "inv_001" in session_state.active_tools
        assert session_state.active_tools["inv_001"].tool_name == "shell"

    def test_completes_tool_invocation(
        self, session_state: SessionState, sample_tool_invocation: ToolInvocation
    ) -> None:
        session_state.update_tool(sample_tool_invocation)
        session_state.complete_tool("inv_001", ToolStatus.COMPLETED)
        assert "inv_001" not in session_state.active_tools

    def test_complete_nonexistent_tool_is_safe(
        self, session_state: SessionState
    ) -> None:
        # Should not raise
        session_state.complete_tool("inv_nonexistent", ToolStatus.FAILED)
