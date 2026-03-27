from __future__ import annotations

import pytest

from breqy.agents.private_memory import PrivateMemoryRuntime, private_memory_result_to_tool_result
from breqy.domain.events import PrivateMemoryOperationRequestedEvent
from breqy.memory.contracts import InMemoryAgentPrivateMemoryStore


@pytest.mark.asyncio
async def test_private_memory_delegated_flow_returns_engine_consumable_tool_result() -> None:
    runtime = PrivateMemoryRuntime(
        agent_id="agt_owner",
        store=InMemoryAgentPrivateMemoryStore(),
    )

    write_request = PrivateMemoryOperationRequestedEvent(
        session_id="ses_123",
        agent_id="agt_owner",
        correlation_id="inv_write",
        invocation_id="inv_write",
        operation_name="write",
        arguments={"content": "Owner-only private memory."},
    )

    write_result = await runtime.handle_operation(write_request)
    write_tool_result = private_memory_result_to_tool_result(write_result)

    assert write_tool_result.success is True
    assert write_tool_result.output["record"]["owner_agent_id"] == "agt_owner"

    search_request = PrivateMemoryOperationRequestedEvent(
        session_id="ses_123",
        agent_id="agt_owner",
        correlation_id="inv_search",
        invocation_id="inv_search",
        operation_name="search",
        arguments={"query": "owner-only", "limit": 10},
    )

    search_result = await runtime.handle_operation(search_request)
    search_tool_result = private_memory_result_to_tool_result(search_result)

    assert search_tool_result.success is True
    assert [record["content"] for record in search_tool_result.output["records"]] == [
        "Owner-only private memory.",
    ]


@pytest.mark.asyncio
async def test_private_memory_delegated_flow_rejects_non_owner_agent() -> None:
    runtime = PrivateMemoryRuntime(
        agent_id="agt_owner",
        store=InMemoryAgentPrivateMemoryStore(),
    )

    result = await runtime.handle_operation(
        PrivateMemoryOperationRequestedEvent(
            session_id="ses_123",
            agent_id="agt_intruder",
            correlation_id="inv_intruder",
            invocation_id="inv_intruder",
            operation_name="search",
            arguments={"query": "owner-only", "limit": 10},
        )
    )
    tool_result = private_memory_result_to_tool_result(result)

    assert tool_result.success is False
    assert tool_result.error == "Cross-agent private memory access denied"
