"""Agent-owned delegated private-memory runtime helpers."""
from __future__ import annotations

from dataclasses import asdict

from breqy.domain.events import (
    PrivateMemoryOperationRequestedEvent,
    PrivateMemoryOperationResultEvent,
)
from breqy.domain.ids import generate_prefixed_id
from breqy.domain.models import StructuredErrorPayload, StructuredResultPayload
from breqy.memory.contracts import AgentPrivateMemoryStore, PrivateMemoryRecord
from breqy.tools.executor import ToolResult


class PrivateMemoryRuntime:
    def __init__(self, *, agent_id: str, store: AgentPrivateMemoryStore) -> None:
        self._agent_id = agent_id
        self._store = store

    async def handle_operation(
        self,
        request: PrivateMemoryOperationRequestedEvent,
    ) -> PrivateMemoryOperationResultEvent:
        if request.agent_id != self._agent_id:
            return self._failure(
                request,
                code="private_memory_denied",
                message="Cross-agent private memory access denied",
                details={"owner_agent_id": self._agent_id},
            )

        if request.operation_name == "write":
            content = str(request.arguments.get("content", "")).strip()
            if not content:
                return self._failure(
                    request,
                    code="private_memory_invalid_arguments",
                    message="Private memory write requires content",
                )
            tags = tuple(
                str(tag).strip()
                for tag in request.arguments.get("tags", [])
                if str(tag).strip()
            )
            record = PrivateMemoryRecord(
                id=generate_prefixed_id("pmr"),
                owner_agent_id=self._agent_id,
                content=content,
                tags=tags,
            )
            await self._store.write(agent_id=self._agent_id, record=record)
            return self._success(
                request,
                summary="Private memory write completed",
                content={"scope": "private", "record": asdict(record)},
            )

        if request.operation_name == "search":
            query = str(request.arguments.get("query", ""))
            limit = request.arguments.get("limit", 10)
            try:
                normalized_limit = int(limit)
            except (TypeError, ValueError):
                return self._failure(
                    request,
                    code="private_memory_invalid_arguments",
                    message="Private memory search requires a valid limit",
                )
            records = await self._store.search(
                agent_id=self._agent_id,
                query=query,
                limit=normalized_limit,
            )
            return self._success(
                request,
                summary="Private memory search completed",
                content={"scope": "private", "records": [asdict(record) for record in records]},
            )

        return self._failure(
            request,
            code="private_memory_invalid_operation",
            message=f"Unsupported private memory operation: {request.operation_name}",
        )

    def _success(
        self,
        request: PrivateMemoryOperationRequestedEvent,
        *,
        summary: str,
        content: dict[str, object],
    ) -> PrivateMemoryOperationResultEvent:
        return PrivateMemoryOperationResultEvent(
            session_id=request.session_id,
            agent_id=request.agent_id,
            correlation_id=request.invocation_id,
            invocation_id=request.invocation_id,
            operation_name=request.operation_name,
            success_payload=StructuredResultPayload(summary=summary, content=content),
        )

    def _failure(
        self,
        request: PrivateMemoryOperationRequestedEvent,
        *,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> PrivateMemoryOperationResultEvent:
        return PrivateMemoryOperationResultEvent(
            session_id=request.session_id,
            agent_id=request.agent_id,
            correlation_id=request.invocation_id,
            invocation_id=request.invocation_id,
            operation_name=request.operation_name,
            failure_payload=StructuredErrorPayload(
                code=code,
                message=message,
                details=details or {},
            ),
        )


def private_memory_result_to_tool_result(
    result: PrivateMemoryOperationResultEvent,
) -> ToolResult:
    if result.success_payload is not None:
        return ToolResult(
            success=True,
            output=dict(result.success_payload.content),
            summary=result.success_payload.summary,
        )

    assert result.failure_payload is not None
    return ToolResult(
        success=False,
        error=result.failure_payload.message,
        output=dict(result.failure_payload.details),
        summary=result.failure_payload.message,
    )
