"""Tests for breqy.domain.events — typed A2A event schemas."""
from __future__ import annotations


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
    from breqy.domain.events import ControlEvent
    from breqy.domain.enums import EventType

    e = ControlEvent(session_id="ses_test", event_type=EventType.CONTROL_STOP)
    assert e.event_type == EventType.CONTROL_STOP
    assert e.new_direction == ""


def test_agent_lifecycle_event():
    from breqy.domain.events import AgentLifecycleEvent
    from breqy.domain.enums import EventType

    e = AgentLifecycleEvent(
        session_id="ses_test",
        event_type=EventType.AGENT_CONNECTED,
        agent_id="agt_test",
    )
    assert e.event_type == EventType.AGENT_CONNECTED
    assert e.agent_id == "agt_test"


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
