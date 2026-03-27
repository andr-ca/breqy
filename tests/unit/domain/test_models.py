"""Tests for breqy.domain enums, models, and errors."""
from __future__ import annotations

from datetime import UTC, datetime

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


def test_memory_scope_values():
    from breqy.domain.enums import MemoryScope

    assert MemoryScope.SESSION == "session"
    assert MemoryScope.GLOBAL == "global"


def test_memory_record_kind_values():
    from breqy.domain.enums import MemoryRecordKind

    assert MemoryRecordKind.NOTE == "note"
    assert MemoryRecordKind.FACT == "fact"
    assert MemoryRecordKind.SUMMARY == "summary"
    assert MemoryRecordKind.LESSON == "lesson"


def test_memory_promotion_status_values():
    from breqy.domain.enums import MemoryPromotionStatus

    assert MemoryPromotionStatus.PENDING == "pending"
    assert MemoryPromotionStatus.APPROVED == "approved"
    assert MemoryPromotionStatus.DENIED == "denied"


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


def test_memory_record_session_shape_supports_explicit_links():
    from breqy.domain.enums import MemoryRecordKind, MemoryScope
    from breqy.domain.models import MemoryRecord

    record = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id="ses_test",
        agent_id="agt_test",
        kind=MemoryRecordKind.NOTE,
        source="agent_note",
        content="Remember to ask about deploy timing.",
        task_id="tsk_test",
        approval_id="apr_test",
        artifact_id="art_test",
        linked_event_id="evt_test",
        promotion_id="mpr_test",
        tags=["handoff", "deploy"],
    )

    assert record.id.startswith("mem_")
    assert record.scope == MemoryScope.SESSION
    assert record.session_id == "ses_test"
    assert record.agent_id == "agt_test"
    assert record.source == "agent_note"
    assert record.task_id == "tsk_test"
    assert record.approval_id == "apr_test"
    assert record.artifact_id == "art_test"
    assert record.linked_event_id == "evt_test"
    assert record.promotion_id == "mpr_test"
    assert record.tags == ["handoff", "deploy"]


def test_memory_record_global_shape_allows_no_session_id():
    from breqy.domain.enums import MemoryRecordKind, MemoryScope
    from breqy.domain.models import MemoryRecord

    record = MemoryRecord(
        scope=MemoryScope.GLOBAL,
        agent_id="agt_test",
        kind=MemoryRecordKind.FACT,
        source="promotion",
        content="User prefers concise answers.",
    )

    assert record.scope == MemoryScope.GLOBAL
    assert record.session_id is None


def test_memory_record_global_shape_rejects_session_id():
    from pydantic import ValidationError

    from breqy.domain.enums import MemoryRecordKind, MemoryScope
    from breqy.domain.models import MemoryRecord

    with pytest.raises(ValidationError):
        MemoryRecord(
            scope=MemoryScope.GLOBAL,
            session_id="ses_test",
            agent_id="agt_test",
            kind=MemoryRecordKind.FACT,
            source="promotion",
            content="User prefers concise answers.",
        )


def test_memory_record_session_shape_requires_session_id() -> None:
    from pydantic import ValidationError

    from breqy.domain.enums import MemoryRecordKind, MemoryScope
    from breqy.domain.models import MemoryRecord

    with pytest.raises(ValidationError, match="session memory records must include session_id"):
        MemoryRecord(
            scope=MemoryScope.SESSION,
            agent_id="agt_test",
            kind=MemoryRecordKind.NOTE,
            source="agent_note",
            content="Remember this.",
        )


def test_memory_promotion_preserves_proposal_status_metadata():
    from breqy.domain.enums import MemoryPromotionStatus
    from breqy.domain.models import MemoryPromotion

    promotion = MemoryPromotion(
        source_record_id="mem_source",
        target_record_id="mem_global",
        source_session_id="ses_test",
        proposing_agent_id="agt_test",
        approval_id="apr_test",
        status=MemoryPromotionStatus.PENDING,
    )

    assert promotion.id.startswith("mpr_")
    assert promotion.source_record_id == "mem_source"
    assert promotion.target_record_id == "mem_global"
    assert promotion.source_session_id == "ses_test"
    assert promotion.proposing_agent_id == "agt_test"
    assert promotion.approval_id == "apr_test"
    assert promotion.status == MemoryPromotionStatus.PENDING


def test_memory_promotion_is_session_to_global_only():
    from pydantic import ValidationError

    from breqy.domain.enums import MemoryPromotionStatus, MemoryScope
    from breqy.domain.models import MemoryPromotion

    with pytest.raises(ValidationError):
        MemoryPromotion(
            source_record_id="mem_source",
            source_session_id="ses_test",
            proposing_agent_id="agt_test",
            status=MemoryPromotionStatus.APPROVED,
            source_scope=MemoryScope.GLOBAL,
            target_scope=MemoryScope.GLOBAL,
        )


def test_memory_promotion_approved_requires_target_record_id():
    from pydantic import ValidationError

    from breqy.domain.enums import MemoryPromotionStatus
    from breqy.domain.models import MemoryPromotion

    with pytest.raises(ValidationError):
        MemoryPromotion(
            source_record_id="mem_source",
            source_session_id="ses_test",
            proposing_agent_id="agt_test",
            status=MemoryPromotionStatus.APPROVED,
        )


def test_memory_record_roundtrip_preserves_source_and_event_id():
    from breqy.domain.enums import MemoryRecordKind, MemoryScope
    from breqy.domain.models import MemoryRecord

    record = MemoryRecord(
        scope=MemoryScope.SESSION,
        session_id="ses_test",
        agent_id="agt_test",
        kind=MemoryRecordKind.LESSON,
        source="promotion_review",
        content="Persist concise response preference.",
        linked_event_id="evt_test",
    )

    restored = MemoryRecord.model_validate(record.model_dump())

    assert restored.source == "promotion_review"
    assert restored.linked_event_id == "evt_test"


def test_memory_promotion_roundtrip_preserves_target_record_id():
    from breqy.domain.enums import MemoryPromotionStatus
    from breqy.domain.models import MemoryPromotion

    promotion = MemoryPromotion(
        source_record_id="mem_source",
        target_record_id="mem_target",
        source_session_id="ses_test",
        proposing_agent_id="agt_test",
        approval_id="apr_test",
        status=MemoryPromotionStatus.APPROVED,
    )

    restored = MemoryPromotion.model_validate(promotion.model_dump())

    assert restored.target_record_id == "mem_target"
    assert restored.status == MemoryPromotionStatus.APPROVED


def test_runtime_auth_enums_cover_phase_8_values():
    from breqy.domain.enums import AuthFlowKind, AuthSessionStatus, CredentialKind

    assert AuthFlowKind.DEVICE == "device"
    assert AuthFlowKind.PKCE_CODE == "pkce_code"
    assert AuthFlowKind.API_KEY == "api_key"
    assert AuthSessionStatus.UNAUTHENTICATED == "unauthenticated"
    assert AuthSessionStatus.IN_PROGRESS == "in_progress"
    assert AuthSessionStatus.AUTHENTICATED == "authenticated"
    assert AuthSessionStatus.FAILED == "failed"
    assert CredentialKind.ACCESS_TOKEN == "access_token"
    assert CredentialKind.API_KEY == "api_key"


def test_structured_result_payload_roundtrip_preserves_content():
    from breqy.domain.models import StructuredResultPayload

    payload = StructuredResultPayload(
        summary="Tool completed successfully.",
        content={"stdout": "done", "exit_code": 0},
        metadata={"tool_name": "shell"},
    )

    restored = StructuredResultPayload.model_validate(payload.model_dump())

    assert restored.summary == "Tool completed successfully."
    assert restored.content["stdout"] == "done"
    assert restored.metadata == {"tool_name": "shell"}


def test_structured_error_payload_defaults_and_roundtrip():
    from breqy.domain.models import StructuredErrorPayload

    payload = StructuredErrorPayload(
        code="tool_failed",
        message="Command exited non-zero.",
        details={"exit_code": 1},
        retryable=True,
    )

    restored = StructuredErrorPayload.model_validate(payload.model_dump())

    assert restored.code == "tool_failed"
    assert restored.message == "Command exited non-zero."
    assert restored.details == {"exit_code": 1}
    assert restored.retryable is True


def test_task_context_reference_captures_optional_metadata():
    from breqy.domain.enums import TaskStatus
    from breqy.domain.models import TaskContextReference

    reference = TaskContextReference(
        task_id="tsk_test",
        title="Finish runtime auth",
        status=TaskStatus.RUNNING,
        summary="Continue provider adapter implementation.",
        parent_task_id="tsk_parent",
    )

    assert reference.task_id == "tsk_test"
    assert reference.status == TaskStatus.RUNNING
    assert reference.summary == "Continue provider adapter implementation."
    assert reference.parent_task_id == "tsk_parent"


def test_provider_credential_roundtrip_preserves_runtime_metadata():
    from pydantic import SecretStr

    from breqy.agents.models import ProviderCredential
    from breqy.domain.enums import CredentialKind

    credential = ProviderCredential(
        provider="claude",
        credential_kind=CredentialKind.ACCESS_TOKEN,
        secret_value="token-value",
        refresh_token="refresh-value",
        expires_at=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        metadata={"account": "default"},
    )

    restored = ProviderCredential.model_validate(credential.model_dump())

    assert restored.provider == "claude"
    assert restored.credential_kind == CredentialKind.ACCESS_TOKEN
    assert isinstance(restored.secret_value, SecretStr)
    assert restored.secret_value.get_secret_value() == "token-value"
    assert "token-value" not in repr(restored)
    assert isinstance(restored.refresh_token, SecretStr)
    assert restored.refresh_token.get_secret_value() == "refresh-value"
    assert "refresh-value" not in repr(restored)
    assert restored.expires_at == datetime(2026, 3, 23, 12, 0, tzinfo=UTC)
    assert restored.metadata == {"account": "default"}


def test_auth_session_tracks_flow_state_for_interactive_login():
    from breqy.agents.models import AuthSession
    from breqy.domain.enums import AuthFlowKind, AuthSessionStatus

    session = AuthSession(
        provider="copilot",
        flow_kind=AuthFlowKind.DEVICE,
        status=AuthSessionStatus.IN_PROGRESS,
        verification_url="https://github.com/login/device",
        user_code="ABCD-EFGH",
        display_message="Enter the code in your browser.",
    )

    assert session.provider == "copilot"
    assert session.flow_kind == AuthFlowKind.DEVICE
    assert session.status == AuthSessionStatus.IN_PROGRESS
    assert session.user_code == "ABCD-EFGH"


def test_auth_status_captures_authenticated_state_and_error_details():
    from breqy.agents.models import AuthStatus
    from breqy.domain.enums import AuthFlowKind, AuthSessionStatus

    status = AuthStatus(
        provider="gemini",
        status=AuthSessionStatus.AUTHENTICATED,
        flow_kind=AuthFlowKind.DEVICE,
        verification_url="https://accounts.example.test/device",
        user_code="ABCD-EFGH",
        display_message="Enter the code in your browser.",
        last_error="",
        authenticated_at=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
    )

    assert status.provider == "gemini"
    assert status.status == AuthSessionStatus.AUTHENTICATED
    assert status.flow_kind == AuthFlowKind.DEVICE
    assert status.verification_url == "https://accounts.example.test/device"
    assert status.user_code == "ABCD-EFGH"
    assert status.display_message == "Enter the code in your browser."
    assert status.authenticated_at == datetime(2026, 3, 23, 12, 0, tzinfo=UTC)
    assert status.last_error == ""


def test_session_context_bundle_embeds_messages_and_task_context():
    from breqy.domain.enums import MessageRole, TaskStatus
    from breqy.domain.models import Message, SessionContextBundle, TaskContextReference

    bundle = SessionContextBundle(
        messages=[
            Message(
                id="msg_test",
                session_id="ses_test",
                role=MessageRole.USER,
                content="Need help with auth.",
            )
        ],
        memory_summary="User is configuring provider credentials.",
        memory_checkpoint="Checkpoint after manifest validation.",
        task_context=TaskContextReference(
            task_id="tsk_test",
            title="Finish runtime auth",
            status=TaskStatus.RUNNING,
        ),
    )

    assert bundle.messages[0].content == "Need help with auth."
    assert bundle.memory_summary == "User is configuring provider credentials."
    assert bundle.memory_checkpoint == "Checkpoint after manifest validation."
    assert bundle.task_context is not None
    assert bundle.task_context.title == "Finish runtime auth"


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
