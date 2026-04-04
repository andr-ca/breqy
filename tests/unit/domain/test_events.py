"""Tests for breqy.domain.events — typed A2A event schemas."""

from __future__ import annotations

from typing import Any, cast

import pytest


def test_event_base_has_required_fields():
    from breqy.domain.events import Event
    from breqy.domain.enums import EventType

    e = Event(event_type=EventType.SESSION_CREATED, session_id="ses_test")
    assert e.event_id is not None
    assert e.event_id.startswith("evt_")
    assert e.schema_version == 1
    assert e.timestamp is not None
    assert e.session_id == "ses_test"
    assert e.event_type == EventType.SESSION_CREATED


def test_message_sent_event():
    from pydantic import ValidationError

    from breqy.domain.events import MessageSentEvent
    from breqy.domain.enums import EventType, MessageRole

    e = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_test",
        role=MessageRole.USER,
        content="Hello",
    )
    assert e.event_type == EventType.MESSAGE_SENT
    assert e.message_id == "msg_test"
    assert e.content == "Hello"

    with pytest.raises(ValidationError):
        MessageSentEvent(
            session_id="ses_test",
            event_type=EventType.TASK_UPDATED,
            message_id="msg_test",
            role=MessageRole.USER,
            content="Hello",
        )


def test_message_chunk_event():
    from breqy.domain.events import MessageChunkEvent
    from breqy.domain.enums import EventType

    e = MessageChunkEvent(
        session_id="ses_test",
        message_id="msg_test",
        chunk="Hello",
        chunk_index=0,
    )
    assert e.event_type == EventType.MESSAGE_CHUNK
    assert e.chunk_index == 0


def test_tool_invocation_started_event():
    from breqy.domain.events import ToolInvocationStartedEvent
    from breqy.domain.enums import EventType

    e = ToolInvocationStartedEvent(
        session_id="ses_test",
        invocation_id="inv_test",
        tool_name="shell",
        arguments={"command": "ls"},
        summary="List files",
    )
    assert e.event_type == EventType.TOOL_INVOCATION_STARTED
    assert e.tool_name == "shell"
    assert e.arguments == {"command": "ls"}


def test_tool_invocation_completed_event():
    from breqy.domain.events import ToolInvocationCompletedEvent
    from breqy.domain.enums import EventType, ToolStatus

    e = ToolInvocationCompletedEvent(
        session_id="ses_test",
        invocation_id="inv_test",
        tool_name="shell",
        status=ToolStatus.COMPLETED,
    )
    assert e.event_type == EventType.TOOL_INVOCATION_COMPLETED
    assert e.status == ToolStatus.COMPLETED


def test_approval_requested_event():
    from breqy.domain.events import ApprovalRequestedEvent
    from breqy.domain.enums import EventType

    e = ApprovalRequestedEvent(
        session_id="ses_test",
        approval_id="apr_test",
        invocation_id="inv_test",
        description="Run rm -rf",
    )
    assert e.event_type == EventType.APPROVAL_REQUESTED
    assert e.approval_id == "apr_test"


def test_control_event_stop():
    from pydantic import ValidationError

    from breqy.domain.events import ControlEvent
    from breqy.domain.enums import EventType

    e = ControlEvent(session_id="ses_test", event_type=EventType.CONTROL_STOP)
    assert e.event_type == EventType.CONTROL_STOP
    assert e.new_direction == ""

    with pytest.raises(ValidationError):
        ControlEvent(session_id="ses_test", event_type=EventType.MESSAGE_SENT)


def test_agent_lifecycle_event():
    from pydantic import ValidationError

    from breqy.domain.events import AgentLifecycleEvent
    from breqy.domain.enums import EventType

    e = AgentLifecycleEvent(
        session_id="ses_test",
        event_type=EventType.AGENT_CONNECTED,
        agent_id="agt_test",
    )
    assert e.event_type == EventType.AGENT_CONNECTED
    assert e.agent_id == "agt_test"

    with pytest.raises(ValidationError):
        AgentLifecycleEvent(
            session_id="ses_test",
            event_type=EventType.AGENT_CONNECTED,
            agent_id="",
        )

    with pytest.raises(ValidationError):
        AgentLifecycleEvent(
            session_id="ses_test",
            event_type=EventType.AGENT_CONNECTED,
        )


def test_task_updated_event_uses_typed_task_status():
    from pydantic import ValidationError

    from breqy.domain.events import TaskUpdatedEvent, deserialize_event
    from breqy.domain.enums import EventType, TaskStatus

    event = TaskUpdatedEvent(
        session_id="ses_test",
        task_id="tsk_test",
        title="Finish runtime auth",
        status=TaskStatus.RUNNING,
    )

    assert event.event_type == EventType.TASK_UPDATED
    assert event.status == TaskStatus.RUNNING

    created = TaskUpdatedEvent(
        session_id="ses_test",
        event_type=EventType.TASK_CREATED,
        task_id="tsk_created",
        title="Create task",
        status=TaskStatus.PENDING,
    )
    completed = TaskUpdatedEvent(
        session_id="ses_test",
        event_type=EventType.TASK_COMPLETED,
        task_id="tsk_completed",
        title="Complete task",
        status=TaskStatus.COMPLETED,
    )

    assert created.event_type == EventType.TASK_CREATED
    assert completed.event_type == EventType.TASK_COMPLETED
    assert isinstance(deserialize_event(created.model_dump()), TaskUpdatedEvent)
    assert isinstance(deserialize_event(completed.model_dump()), TaskUpdatedEvent)

    with pytest.raises(ValidationError):
        TaskUpdatedEvent(
            session_id="ses_test",
            task_id="tsk_test",
            title="Finish runtime auth",
            status="not_a_real_status",
        )

    with pytest.raises(ValidationError):
        TaskUpdatedEvent(
            session_id="ses_test",
            event_type=EventType.MESSAGE_SENT,
            task_id="tsk_test",
            title="Finish runtime auth",
            status=TaskStatus.RUNNING,
        )


def test_approval_decided_event_requires_matching_event_type_and_decision():
    from pydantic import ValidationError

    from breqy.domain.events import ApprovalDecidedEvent
    from breqy.domain.enums import ApprovalStatus, EventType

    granted = ApprovalDecidedEvent(
        session_id="ses_test",
        approval_id="apr_test",
        event_type=EventType.APPROVAL_GRANTED,
        decision=ApprovalStatus.GRANTED,
    )
    denied = ApprovalDecidedEvent(
        session_id="ses_test",
        approval_id="apr_test",
        event_type=EventType.APPROVAL_DENIED,
        decision=ApprovalStatus.DENIED,
    )

    assert granted.decision == ApprovalStatus.GRANTED
    assert denied.decision == ApprovalStatus.DENIED

    with pytest.raises(ValidationError):
        ApprovalDecidedEvent(
            session_id="ses_test",
            approval_id="apr_test",
            event_type=EventType.APPROVAL_GRANTED,
            decision=ApprovalStatus.DENIED,
        )

    with pytest.raises(ValidationError):
        ApprovalDecidedEvent(
            session_id="ses_test",
            approval_id="apr_test",
            event_type=EventType.APPROVAL_DENIED,
            decision=ApprovalStatus.GRANTED,
        )

    with pytest.raises(ValidationError):
        ApprovalDecidedEvent(
            session_id="ses_test",
            approval_id="apr_test",
            event_type=EventType.MESSAGE_SENT,
            decision=ApprovalStatus.GRANTED,
        )


def test_event_roundtrip():
    from breqy.domain.events import MessageSentEvent
    from breqy.domain.enums import MessageRole

    e = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_test",
        role=MessageRole.USER,
        content="Hello",
    )
    dumped = e.model_dump()
    restored = MessageSentEvent.model_validate(dumped)
    assert restored.event_id == e.event_id
    assert restored.content == e.content


def test_event_dump_json():
    from breqy.domain.events import MessageSentEvent
    from breqy.domain.enums import MessageRole
    import json

    e = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_test",
        role=MessageRole.USER,
        content="Hello",
    )
    json_str = e.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["event_id"] == e.event_id


def test_deserialize_event_message_sent():
    from breqy.domain.events import deserialize_event, MessageSentEvent
    from breqy.domain.enums import MessageRole

    e = MessageSentEvent(
        session_id="ses_test",
        message_id="msg_test",
        role=MessageRole.USER,
        content="Hello",
    )
    data = e.model_dump()
    result = deserialize_event(data)
    assert isinstance(result, MessageSentEvent)
    assert result.event_id == e.event_id


def test_deserialize_event_control():
    from breqy.domain.events import deserialize_event, ControlEvent
    from breqy.domain.enums import EventType

    e = ControlEvent(session_id="ses_test", event_type=EventType.CONTROL_STOP)
    data = e.model_dump()
    result = deserialize_event(data)
    assert isinstance(result, ControlEvent)


def test_event_type_map_covers_all_event_types():
    from breqy.domain.events import EVENT_TYPE_MAP
    from breqy.domain.enums import EventType

    for event_type in EventType:
        assert event_type in EVENT_TYPE_MAP, (
            f"EventType.{event_type.name} not registered in EVENT_TYPE_MAP"
        )


def test_memory_record_created_event():
    from breqy.domain.events import MemoryRecordCreatedEvent
    from breqy.domain.enums import EventType, MemoryRecordKind, MemoryScope

    event = MemoryRecordCreatedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        record_id="mem_test",
        scope=MemoryScope.SESSION,
        kind=MemoryRecordKind.NOTE,
        source="agent_note",
        content="Remember project constraints.",
        task_id="tsk_test",
        approval_id="apr_test",
        artifact_id="art_test",
        linked_event_id="evt_linked",
        promotion_id="mpr_test",
    )

    assert event.event_type == EventType.MEMORY_RECORD_CREATED
    assert event.record_id == "mem_test"
    assert event.scope == MemoryScope.SESSION
    assert event.source == "agent_note"
    assert event.linked_event_id == "evt_linked"


def test_memory_record_created_event_roundtrip_preserves_source_and_event_link():
    from breqy.domain.events import MemoryRecordCreatedEvent
    from breqy.domain.enums import MemoryRecordKind, MemoryScope

    event = MemoryRecordCreatedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        record_id="mem_test",
        scope=MemoryScope.SESSION,
        kind=MemoryRecordKind.NOTE,
        source="agent_note",
        content="Remember project constraints.",
        linked_event_id="evt_linked",
    )

    restored = MemoryRecordCreatedEvent.model_validate(event.model_dump())

    assert restored.source == "agent_note"
    assert restored.linked_event_id == "evt_linked"


def test_memory_record_updated_event():
    from breqy.domain.events import MemoryRecordUpdatedEvent
    from breqy.domain.enums import EventType, MemoryRecordKind, MemoryScope

    event = MemoryRecordUpdatedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        record_id="mem_test",
        scope=MemoryScope.SESSION,
        kind=MemoryRecordKind.SUMMARY,
        source="checkpoint",
        content="Updated summary.",
    )

    assert event.event_type == EventType.MEMORY_RECORD_UPDATED
    assert event.kind == MemoryRecordKind.SUMMARY


def test_memory_promotion_requested_event():
    from breqy.domain.events import MemoryPromotionRequestedEvent
    from breqy.domain.enums import EventType, MemoryPromotionStatus

    event = MemoryPromotionRequestedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        promotion_id="mpr_test",
        source_record_id="mem_session",
        approval_id="apr_test",
        status=MemoryPromotionStatus.PENDING,
    )

    assert event.event_type == EventType.MEMORY_PROMOTION_REQUESTED
    assert event.status == MemoryPromotionStatus.PENDING


def test_memory_promotion_requested_event_rejects_non_pending_status():
    from pydantic import ValidationError

    from breqy.domain.events import MemoryPromotionRequestedEvent
    from breqy.domain.enums import MemoryPromotionStatus

    with pytest.raises(ValidationError):
        MemoryPromotionRequestedEvent(
            session_id="ses_test",
            agent_id="agt_test",
            promotion_id="mpr_test",
            source_record_id="mem_session",
            status=MemoryPromotionStatus.APPROVED,
        )


def test_memory_promotion_approved_event():
    from breqy.domain.events import MemoryPromotionApprovedEvent
    from breqy.domain.enums import EventType, MemoryPromotionStatus

    event = MemoryPromotionApprovedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        promotion_id="mpr_test",
        source_record_id="mem_session",
        target_record_id="mem_global",
        approval_id="apr_test",
        status=MemoryPromotionStatus.APPROVED,
    )

    assert event.event_type == EventType.MEMORY_PROMOTION_APPROVED
    assert event.target_record_id == "mem_global"
    assert event.status == MemoryPromotionStatus.APPROVED


def test_memory_promotion_approved_event_rejects_denied_status():
    from pydantic import ValidationError

    from breqy.domain.events import MemoryPromotionApprovedEvent
    from breqy.domain.enums import MemoryPromotionStatus

    with pytest.raises(ValidationError):
        MemoryPromotionApprovedEvent(
            session_id="ses_test",
            agent_id="agt_test",
            promotion_id="mpr_test",
            source_record_id="mem_session",
            target_record_id="mem_global",
            status=MemoryPromotionStatus.DENIED,
        )


def test_memory_promotion_denied_event():
    from breqy.domain.events import MemoryPromotionDeniedEvent
    from breqy.domain.enums import EventType, MemoryPromotionStatus

    event = MemoryPromotionDeniedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        promotion_id="mpr_test",
        source_record_id="mem_session",
        approval_id="apr_test",
        status=MemoryPromotionStatus.DENIED,
        reason="Needs human review.",
    )

    assert event.event_type == EventType.MEMORY_PROMOTION_DENIED
    assert event.reason == "Needs human review."
    assert event.status == MemoryPromotionStatus.DENIED


def test_memory_promotion_denied_event_rejects_approved_status():
    from pydantic import ValidationError

    from breqy.domain.events import MemoryPromotionDeniedEvent
    from breqy.domain.enums import MemoryPromotionStatus

    with pytest.raises(ValidationError):
        MemoryPromotionDeniedEvent(
            session_id="ses_test",
            agent_id="agt_test",
            promotion_id="mpr_test",
            source_record_id="mem_session",
            status=MemoryPromotionStatus.APPROVED,
        )


def test_private_memory_operation_result_requires_exactly_one_payload():
    from pydantic import ValidationError

    from breqy.domain.events import PrivateMemoryOperationResultEvent

    with pytest.raises(ValidationError, match="exactly one outcome payload"):
        PrivateMemoryOperationResultEvent(
            session_id="ses_test",
            agent_id="agt_test",
            correlation_id="inv_test",
            invocation_id="inv_test",
            operation_name="search",
        )


def test_memory_promotion_requested_event_rejects_wrong_event_type():
    from breqy.domain.events import MemoryPromotionRequestedEvent
    from breqy.domain.enums import EventType

    with pytest.raises(ValueError, match="memory.promotion.requested"):
        cast(
            Any,
            MemoryPromotionRequestedEvent.model_construct(
                session_id="ses_test",
                event_type=EventType.MEMORY_PROMOTION_APPROVED,
                promotion_id="mpr_test",
                source_record_id="mem_test",
            ),
        ).validate_requested_status()


def test_memory_promotion_approved_event_rejects_wrong_event_type():
    from breqy.domain.events import MemoryPromotionApprovedEvent
    from breqy.domain.enums import EventType

    with pytest.raises(ValueError, match="memory.promotion.approved"):
        cast(
            Any,
            MemoryPromotionApprovedEvent.model_construct(
                session_id="ses_test",
                event_type=EventType.MEMORY_PROMOTION_DENIED,
                promotion_id="mpr_test",
                source_record_id="mem_source",
                target_record_id="mem_target",
            ),
        ).validate_approved_status()


def test_memory_promotion_denied_event_rejects_wrong_event_type():
    from breqy.domain.events import MemoryPromotionDeniedEvent
    from breqy.domain.enums import EventType

    with pytest.raises(ValueError, match="memory.promotion.denied"):
        cast(
            Any,
            MemoryPromotionDeniedEvent.model_construct(
                session_id="ses_test",
                event_type=EventType.MEMORY_PROMOTION_APPROVED,
                promotion_id="mpr_test",
                source_record_id="mem_source",
            ),
        ).validate_denied_status()


def test_deserialize_event_memory_record_created():
    from breqy.domain.events import MemoryRecordCreatedEvent, deserialize_event
    from breqy.domain.enums import MemoryRecordKind, MemoryScope

    event = MemoryRecordCreatedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        record_id="mem_test",
        scope=MemoryScope.SESSION,
        kind=MemoryRecordKind.NOTE,
        source="agent_note",
        content="Remember project constraints.",
    )

    result = deserialize_event(event.model_dump())

    assert isinstance(result, MemoryRecordCreatedEvent)
    assert result.record_id == "mem_test"
    assert result.source == "agent_note"


def test_deserialize_event_unknown_type_falls_back_to_base_event():
    from pydantic import ValidationError

    from breqy.domain.events import deserialize_event

    with pytest.raises(ValidationError):
        deserialize_event({"event_type": "unknown.event", "session_id": "ses_test"})


def test_agent_work_requested_event_embeds_session_context_and_active_skills():
    from pydantic import ValidationError

    from breqy.domain.enums import EventType, MessageRole, TaskStatus
    from breqy.domain.events import AgentWorkRequestedEvent
    from breqy.domain.models import Message, SessionContextBundle, TaskContextReference

    context_bundle = SessionContextBundle(
        messages=[
            Message(
                id="msg_previous",
                session_id="ses_test",
                role=MessageRole.USER,
                content="Earlier context",
            )
        ],
        memory_summary="User prefers concise answers.",
        memory_checkpoint="Checkpoint after previous tool call.",
        task_context=TaskContextReference(
            task_id="tsk_test",
            title="Finish runtime auth",
            status=TaskStatus.RUNNING,
        ),
    )

    event = AgentWorkRequestedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        correlation_id="corr_turn_1",
        message_id="msg_current",
        user_message_content="Continue implementation",
        session_context=context_bundle,
        task_context=TaskContextReference(
            task_id="tsk_test",
            title="Finish runtime auth",
            status=TaskStatus.RUNNING,
        ),
        active_skill_ids=["phase-8-runtime", "tooling"],
    )

    assert event.event_type == EventType.AGENT_WORK_REQUESTED
    assert event.message_id == "msg_current"
    assert event.user_message_content == "Continue implementation"
    assert event.session_context.memory_summary == "User prefers concise answers."
    assert event.session_context.task_context is not None
    assert event.session_context.task_context.task_id == "tsk_test"
    assert event.task_context is not None
    assert event.task_context.task_id == "tsk_test"
    assert event.active_skill_ids == ["phase-8-runtime", "tooling"]

    with pytest.raises(ValidationError):
        AgentWorkRequestedEvent(
            session_id="ses_test",
            agent_id="agt_test",
            correlation_id="corr_turn_1",
            message_id="msg_current",
            user_message_content="Continue implementation",
            session_context=context_bundle,
            task_context=TaskContextReference(
                task_id="tsk_other",
                title="Mismatched task context",
                status=TaskStatus.RUNNING,
            ),
        )

    with pytest.raises(ValidationError):
        AgentWorkRequestedEvent(
            session_id="ses_test",
            correlation_id="corr_turn_1",
            message_id="msg_current",
            user_message_content="Continue implementation",
            session_context=context_bundle,
        )

    with pytest.raises(ValidationError):
        AgentWorkRequestedEvent(
            session_id="ses_test",
            agent_id="agt_test",
            message_id="msg_current",
            user_message_content="Continue implementation",
            session_context=context_bundle,
        )


def test_tool_execution_requested_event_captures_normalized_arguments():
    from pydantic import ValidationError

    from breqy.domain.enums import EventType
    from breqy.domain.events import ToolExecutionRequestedEvent

    event = ToolExecutionRequestedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        correlation_id="inv_test",
        invocation_id="inv_test",
        tool_name="shell",
        arguments={"command": "ls", "timeout_ms": 1000},
    )

    assert event.event_type == EventType.TOOL_EXECUTION_REQUESTED
    assert event.invocation_id == "inv_test"
    assert event.tool_name == "shell"
    assert event.arguments == {"command": "ls", "timeout_ms": 1000}

    with pytest.raises(ValidationError):
        ToolExecutionRequestedEvent(
            session_id="ses_test",
            correlation_id="inv_test",
            invocation_id="inv_test",
            tool_name="shell",
            arguments={"command": "ls"},
        )

    with pytest.raises(ValidationError):
        ToolExecutionRequestedEvent(
            session_id="ses_test",
            agent_id="agt_test",
            invocation_id="inv_test",
            tool_name="shell",
            arguments={"command": "ls"},
        )

    with pytest.raises(ValidationError):
        ToolExecutionRequestedEvent(
            session_id="ses_test",
            agent_id="agt_test",
            correlation_id="corr_other",
            invocation_id="inv_test",
            tool_name="shell",
            arguments={"command": "ls"},
        )

    with pytest.raises(ValidationError):
        ToolExecutionRequestedEvent(
            session_id="ses_test",
            event_type=EventType.MESSAGE_SENT,
            agent_id="agt_test",
            correlation_id="inv_test",
            invocation_id="inv_test",
            tool_name="shell",
            arguments={"command": "ls"},
        )


def test_tool_execution_result_event_carries_structured_success_payload():
    from pydantic import ValidationError

    from breqy.domain.enums import EventType
    from breqy.domain.events import ToolExecutionResultEvent
    from breqy.domain.models import StructuredErrorPayload, StructuredResultPayload

    event = ToolExecutionResultEvent(
        session_id="ses_test",
        agent_id="agt_test",
        correlation_id="inv_test",
        invocation_id="inv_test",
        success_payload=StructuredResultPayload(
            summary="Command completed.",
            content={"stdout": "ok", "exit_code": 0},
        ),
    )

    assert event.event_type == EventType.TOOL_EXECUTION_RESULT
    assert event.invocation_id == "inv_test"
    assert event.success_payload is not None
    assert event.success_payload.content["stdout"] == "ok"
    assert event.failure_payload is None

    with pytest.raises(ValidationError):
        ToolExecutionResultEvent(
            session_id="ses_test",
            agent_id="agt_test",
            correlation_id="inv_test",
            invocation_id="inv_test",
            success_payload=StructuredResultPayload(content={"stdout": "ok"}),
            failure_payload=StructuredErrorPayload(message="should fail"),
        )

    with pytest.raises(ValidationError):
        ToolExecutionResultEvent(
            session_id="ses_test",
            correlation_id="inv_test",
            invocation_id="inv_test",
            success_payload=StructuredResultPayload(content={"stdout": "ok"}),
        )

    with pytest.raises(ValidationError):
        ToolExecutionResultEvent(
            session_id="ses_test",
            agent_id="agt_test",
            invocation_id="inv_test",
            success_payload=StructuredResultPayload(content={"stdout": "ok"}),
        )

    with pytest.raises(ValidationError):
        ToolExecutionResultEvent(
            session_id="ses_test",
            agent_id="agt_test",
            correlation_id="corr_other",
            invocation_id="inv_test",
            success_payload=StructuredResultPayload(content={"stdout": "ok"}),
        )


def test_private_memory_operation_requested_event_tracks_operation_details():
    from pydantic import ValidationError

    from breqy.domain.enums import EventType
    from breqy.domain.events import PrivateMemoryOperationRequestedEvent

    event = PrivateMemoryOperationRequestedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        correlation_id="inv_test",
        invocation_id="inv_test",
        operation_name="search",
        arguments={"query": "auth", "limit": 5},
    )

    assert event.event_type == EventType.PRIVATE_MEMORY_OPERATION_REQUESTED
    assert event.operation_name == "search"
    assert event.arguments == {"query": "auth", "limit": 5}

    with pytest.raises(ValidationError):
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_test",
            correlation_id="inv_test",
            invocation_id="inv_test",
            operation_name="search",
            arguments={"query": "auth", "limit": 5},
        )

    with pytest.raises(ValidationError):
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_test",
            agent_id="agt_test",
            invocation_id="inv_test",
            operation_name="search",
            arguments={"query": "auth", "limit": 5},
        )

    with pytest.raises(ValidationError):
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_test",
            agent_id="agt_test",
            correlation_id="corr_other",
            invocation_id="inv_test",
            operation_name="search",
            arguments={"query": "auth", "limit": 5},
        )


def test_private_memory_operation_result_event_carries_structured_failure_payload():
    from pydantic import ValidationError

    from breqy.domain.enums import EventType
    from breqy.domain.events import PrivateMemoryOperationResultEvent
    from breqy.domain.models import StructuredErrorPayload

    event = PrivateMemoryOperationResultEvent(
        session_id="ses_test",
        agent_id="agt_test",
        correlation_id="inv_test",
        invocation_id="inv_test",
        operation_name="search",
        failure_payload=StructuredErrorPayload(
            code="private_memory_denied",
            message="Cross-agent access denied.",
            details={"owner_agent_id": "agt_other"},
        ),
    )

    assert event.event_type == EventType.PRIVATE_MEMORY_OPERATION_RESULT
    assert event.failure_payload is not None
    assert event.failure_payload.code == "private_memory_denied"
    assert event.success_payload is None

    with pytest.raises(ValidationError):
        PrivateMemoryOperationResultEvent(
            session_id="ses_test",
            correlation_id="inv_test",
            invocation_id="inv_test",
            operation_name="search",
            failure_payload=StructuredErrorPayload(message="Cross-agent access denied."),
        )

    with pytest.raises(ValidationError):
        PrivateMemoryOperationResultEvent(
            session_id="ses_test",
            agent_id="agt_test",
            invocation_id="inv_test",
            operation_name="search",
            failure_payload=StructuredErrorPayload(message="Cross-agent access denied."),
        )

    with pytest.raises(ValidationError):
        PrivateMemoryOperationResultEvent(
            session_id="ses_test",
            agent_id="agt_test",
            correlation_id="corr_other",
            invocation_id="inv_test",
            operation_name="search",
            failure_payload=StructuredErrorPayload(message="Cross-agent access denied."),
        )


def test_deserialize_event_agent_work_requested():
    from breqy.domain.enums import MessageRole
    from breqy.domain.events import AgentWorkRequestedEvent, deserialize_event
    from breqy.domain.models import Message, SessionContextBundle

    event = AgentWorkRequestedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        correlation_id="corr_turn_1",
        message_id="msg_current",
        user_message_content="Continue implementation",
        session_context=SessionContextBundle(
            messages=[
                Message(
                    id="msg_previous",
                    session_id="ses_test",
                    role=MessageRole.USER,
                    content="Earlier context",
                )
            ]
        ),
        active_skill_ids=["phase-8-runtime"],
    )

    result = deserialize_event(event.model_dump())

    assert isinstance(result, AgentWorkRequestedEvent)
    assert result.session_context.messages[0].content == "Earlier context"


# --------------------------------------------------------------------------- #
# SessionCreateRequestedEvent
# --------------------------------------------------------------------------- #


def test_session_create_requested_event():
    from breqy.domain.events import SessionCreateRequestedEvent
    from breqy.domain.enums import EventType

    e = SessionCreateRequestedEvent(
        session_id="",
        requested_agent_id="agt_default",
    )
    assert e.event_type == EventType.SESSION_CREATE_REQUESTED
    assert e.requested_agent_id == "agt_default"


def test_session_create_requested_event_defaults():
    from breqy.domain.events import SessionCreateRequestedEvent

    e = SessionCreateRequestedEvent(session_id="")
    assert e.requested_agent_id == "default"


def test_session_create_requested_event_rejects_wrong_type():
    from pydantic import ValidationError
    from breqy.domain.events import SessionCreateRequestedEvent
    from breqy.domain.enums import EventType

    with pytest.raises(ValidationError):
        SessionCreateRequestedEvent(
            session_id="",
            event_type=EventType.SESSION_CREATED,
        )


def test_session_create_requested_event_roundtrip_via_deserialize():
    from breqy.domain.events import SessionCreateRequestedEvent, deserialize_event

    event = SessionCreateRequestedEvent(
        session_id="",
        requested_agent_id="agt_custom",
    )
    result = deserialize_event(event.model_dump())
    assert isinstance(result, SessionCreateRequestedEvent)
    assert result.requested_agent_id == "agt_custom"


# --------------------------------------------------------------------------- #
# AgentWorkRequestedEvent: available_tools field
# --------------------------------------------------------------------------- #


def test_agent_work_requested_event_carries_available_tools():
    """AgentWorkRequestedEvent.available_tools transports ToolDefinition objects."""
    from breqy.agents.providers.base import ToolDefinition
    from breqy.domain.events import AgentWorkRequestedEvent
    from breqy.domain.models import SessionContextBundle

    shell_def = ToolDefinition(
        name="shell",
        description="Execute shell commands",
        input_schema={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    )

    event = AgentWorkRequestedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        correlation_id="corr_1",
        message_id="msg_1",
        user_message_content="run ls",
        session_context=SessionContextBundle(messages=[]),
        available_tools=[shell_def],
    )

    assert len(event.available_tools) == 1
    assert event.available_tools[0].name == "shell"
    assert event.available_tools[0].input_schema["required"] == ["command"]


def test_agent_work_requested_event_available_tools_defaults_empty():
    """available_tools defaults to empty list for backward compatibility."""
    from breqy.domain.events import AgentWorkRequestedEvent
    from breqy.domain.models import SessionContextBundle

    event = AgentWorkRequestedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        correlation_id="corr_1",
        message_id="msg_1",
        user_message_content="hello",
        session_context=SessionContextBundle(messages=[]),
    )

    assert event.available_tools == []


def test_agent_work_requested_event_available_tools_roundtrip():
    """available_tools survive serialize/deserialize roundtrip."""
    from breqy.agents.providers.base import ToolDefinition
    from breqy.domain.events import AgentWorkRequestedEvent, deserialize_event
    from breqy.domain.models import SessionContextBundle

    shell_def = ToolDefinition(
        name="shell",
        description="Execute shell commands",
        input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
    )
    fs_def = ToolDefinition(
        name="filesystem",
        description="Filesystem operations",
        input_schema={"type": "object", "properties": {"operation": {"type": "string"}}},
    )

    event = AgentWorkRequestedEvent(
        session_id="ses_test",
        agent_id="agt_test",
        correlation_id="corr_1",
        message_id="msg_1",
        user_message_content="read file",
        session_context=SessionContextBundle(messages=[]),
        available_tools=[shell_def, fs_def],
    )

    restored = deserialize_event(event.model_dump())

    assert isinstance(restored, AgentWorkRequestedEvent)
    assert len(restored.available_tools) == 2
    assert restored.available_tools[0].name == "shell"
    assert restored.available_tools[1].name == "filesystem"
