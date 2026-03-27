"""Tests for agent-owned private-memory runtime helpers."""
from __future__ import annotations

import pytest

from breqy.domain.events import PrivateMemoryOperationRequestedEvent
from breqy.memory.contracts import InMemoryAgentPrivateMemoryStore
from breqy.agents.private_memory import PrivateMemoryRuntime, private_memory_result_to_tool_result


@pytest.mark.asyncio
async def test_private_memory_runtime_handles_same_agent_write_and_search_round_trip() -> None:
    runtime = PrivateMemoryRuntime(
        agent_id="agt_owner",
        store=InMemoryAgentPrivateMemoryStore(),
    )

    write_result = await runtime.handle_operation(
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_123",
            agent_id="agt_owner",
            correlation_id="inv_write",
            invocation_id="inv_write",
            operation_name="write",
            arguments={
                "content": "Remember the deploy checklist.",
                "tags": ["deploy", "checklist"],
            },
        )
    )

    assert write_result.success_payload is not None
    assert write_result.failure_payload is None
    assert write_result.success_payload.content["record"]["owner_agent_id"] == "agt_owner"

    search_result = await runtime.handle_operation(
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_123",
            agent_id="agt_owner",
            correlation_id="inv_search",
            invocation_id="inv_search",
            operation_name="search",
            arguments={"query": "deploy", "limit": 5},
        )
    )

    assert search_result.success_payload is not None
    assert search_result.success_payload.content["scope"] == "private"
    assert [record["content"] for record in search_result.success_payload.content["records"]] == [
        "Remember the deploy checklist.",
    ]


@pytest.mark.asyncio
async def test_private_memory_runtime_rejects_cross_agent_operations() -> None:
    runtime = PrivateMemoryRuntime(
        agent_id="agt_owner",
        store=InMemoryAgentPrivateMemoryStore(),
    )

    result = await runtime.handle_operation(
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_123",
            agent_id="agt_other",
            correlation_id="inv_forbidden",
            invocation_id="inv_forbidden",
            operation_name="search",
            arguments={"query": "anything"},
        )
    )

    assert result.success_payload is None
    assert result.failure_payload is not None
    assert result.failure_payload.code == "private_memory_denied"
    assert result.failure_payload.details == {"owner_agent_id": "agt_owner"}


@pytest.mark.asyncio
async def test_private_memory_runtime_rejects_unknown_operations() -> None:
    runtime = PrivateMemoryRuntime(
        agent_id="agt_owner",
        store=InMemoryAgentPrivateMemoryStore(),
    )

    result = await runtime.handle_operation(
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_123",
            agent_id="agt_owner",
            correlation_id="inv_unknown",
            invocation_id="inv_unknown",
            operation_name="delete",
            arguments={},
        )
    )

    assert result.success_payload is None
    assert result.failure_payload is not None
    assert result.failure_payload.code == "private_memory_invalid_operation"


@pytest.mark.asyncio
async def test_private_memory_result_to_tool_result_converts_success_payload() -> None:
    runtime = PrivateMemoryRuntime(
        agent_id="agt_owner",
        store=InMemoryAgentPrivateMemoryStore(),
    )
    result_event = await runtime.handle_operation(
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_123",
            agent_id="agt_owner",
            correlation_id="inv_write",
            invocation_id="inv_write",
            operation_name="write",
            arguments={"content": "Keep this private."},
        )
    )

    tool_result = private_memory_result_to_tool_result(result_event)

    assert tool_result.success is True
    assert tool_result.output["scope"] == "private"
    assert tool_result.summary == "Private memory write completed"


@pytest.mark.asyncio
async def test_private_memory_runtime_rejects_blank_write_content() -> None:
    runtime = PrivateMemoryRuntime(
        agent_id="agt_owner",
        store=InMemoryAgentPrivateMemoryStore(),
    )

    result = await runtime.handle_operation(
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_123",
            agent_id="agt_owner",
            correlation_id="inv_blank",
            invocation_id="inv_blank",
            operation_name="write",
            arguments={"content": "   "},
        )
    )

    assert result.failure_payload is not None
    assert result.failure_payload.code == "private_memory_invalid_arguments"


@pytest.mark.asyncio
async def test_private_memory_runtime_rejects_invalid_search_limit() -> None:
    runtime = PrivateMemoryRuntime(
        agent_id="agt_owner",
        store=InMemoryAgentPrivateMemoryStore(),
    )

    result = await runtime.handle_operation(
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_123",
            agent_id="agt_owner",
            correlation_id="inv_bad_limit",
            invocation_id="inv_bad_limit",
            operation_name="search",
            arguments={"query": "deploy", "limit": "bad"},
        )
    )

    assert result.failure_payload is not None
    assert result.failure_payload.code == "private_memory_invalid_arguments"


@pytest.mark.asyncio
async def test_private_memory_result_to_tool_result_converts_failure_payload() -> None:
    runtime = PrivateMemoryRuntime(
        agent_id="agt_owner",
        store=InMemoryAgentPrivateMemoryStore(),
    )
    result_event = await runtime.handle_operation(
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_123",
            agent_id="agt_other",
            correlation_id="inv_forbidden",
            invocation_id="inv_forbidden",
            operation_name="search",
            arguments={"query": "secret"},
        )
    )

    tool_result = private_memory_result_to_tool_result(result_event)

    assert tool_result.success is False
    assert tool_result.error == "Cross-agent private memory access denied"
    assert tool_result.output == {"owner_agent_id": "agt_owner"}
