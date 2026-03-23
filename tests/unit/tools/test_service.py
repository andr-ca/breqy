from __future__ import annotations

from typing import Any

import pytest

from breqy.domain.enums import FilesystemOperation, PolicyAction, ToolStatus
from breqy.domain.events import (
    ApprovalRequestedEvent,
    ToolInvocationCompletedEvent,
    ToolInvocationFailedEvent,
    ToolInvocationStartedEvent,
)
from breqy.domain.models import ToolInvocation
from breqy.policy.models import PolicyDecision
from breqy.tools.executor import ToolExecutor, ToolResult
from breqy.tools.service import ToolService


class RecordingTool(ToolExecutor):
    def __init__(
        self,
        *,
        name: str,
        result: ToolResult | None = None,
        error: Exception | None = None,
        log: list[str] | None = None,
    ) -> None:
        self.name = name
        self.description = f"{name} tool"
        self._result = result or ToolResult(success=True, output={"ok": True}, summary="done")
        self._error = error
        self._log = log if log is not None else []
        self.calls: list[dict[str, Any]] = []

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        self.calls.append(arguments)
        self._log.append("tool.execute")
        if self._error is not None:
            raise self._error
        return self._result


class RecordingToolRegistry:
    def __init__(self, tools: dict[str, ToolExecutor] | None = None) -> None:
        self._tools = tools or {}

    def get(self, name: str) -> ToolExecutor | None:
        return self._tools.get(name)


class StubPolicyEvaluator:
    def __init__(self, action: PolicyAction) -> None:
        self.action = action
        self.calls: list[tuple[str, str, str]] = []

    def evaluate(self, resource: str, agent_id: str = "", session_id: str = "") -> PolicyDecision:
        self.calls.append((resource, agent_id, session_id))
        return PolicyDecision(action=self.action, reason=f"decision:{self.action}")


class RecordingFilesystemPolicyChecker:
    def __init__(self, action: PolicyAction = PolicyAction.ALLOW) -> None:
        self.action = action
        self.calls: list[tuple[str, FilesystemOperation]] = []

    def check(self, path: str, operation: FilesystemOperation) -> PolicyAction:
        self.calls.append((path, operation))
        return self.action


class RecordingApprovalService:
    def __init__(self, *, granted: bool = True, request_id: str = "apr_test", log: list[str] | None = None) -> None:
        self.granted = granted
        self.request_id = request_id
        self._log = log if log is not None else []
        self.request_calls: list[tuple[str, str, str, str]] = []
        self.wait_calls: list[tuple[str, float]] = []

    async def request_approval(
        self,
        session_id: str,
        agent_id: str,
        tool_invocation_id: str,
        description: str,
    ) -> str:
        self.request_calls.append((session_id, agent_id, tool_invocation_id, description))
        self._log.append("approval.request")
        return self.request_id

    async def wait_for_decision(self, request_id: str, timeout: float = 300.0) -> bool:
        self.wait_calls.append((request_id, timeout))
        self._log.append("approval.wait")
        return self.granted


class RecordingInvocationRepository:
    def __init__(self, log: list[str] | None = None) -> None:
        self._log = log if log is not None else []
        self.created: list[ToolInvocation] = []
        self.updates: list[dict[str, Any]] = []

    async def create(self, invocation: ToolInvocation) -> None:
        self.created.append(invocation)
        self._log.append("repo.create")

    async def update_result(
        self,
        invocation_id: str,
        status: ToolStatus,
        result: dict[str, Any] | None,
        error: str,
        summary: str,
        approval_id: str | None = None,
    ) -> None:
        self.updates.append(
            {
                "invocation_id": invocation_id,
                "status": status,
                "result": result,
                "error": error,
                "summary": summary,
                "approval_id": approval_id,
            }
        )
        self._log.append(f"repo.update:{status.value}")


class RecordingEventBus:
    def __init__(self, log: list[str] | None = None) -> None:
        self._log = log if log is not None else []
        self.events: list[object] = []

    async def publish(self, event: object) -> None:
        self.events.append(event)
        if isinstance(event, ApprovalRequestedEvent):
            self._log.append("event.approval_requested")
        elif isinstance(event, ToolInvocationStartedEvent):
            self._log.append("event.started")
        elif isinstance(event, ToolInvocationCompletedEvent):
            self._log.append("event.completed")
        elif isinstance(event, ToolInvocationFailedEvent):
            self._log.append("event.failed")


def build_service(
    *,
    tool: ToolExecutor | None,
    tool_policy_action: PolicyAction = PolicyAction.ALLOW,
    filesystem_policy_action: PolicyAction = PolicyAction.ALLOW,
    approval_granted: bool = True,
    log: list[str] | None = None,
) -> tuple[ToolService, RecordingInvocationRepository, RecordingApprovalService, RecordingEventBus, RecordingFilesystemPolicyChecker]:
    log = log if log is not None else []
    service = ToolService(
        registry=RecordingToolRegistry({tool.name: tool} if tool is not None else {}),
        policy_evaluator=StubPolicyEvaluator(tool_policy_action),
        filesystem_policy_checker=RecordingFilesystemPolicyChecker(filesystem_policy_action),
        approval_service=RecordingApprovalService(granted=approval_granted, log=log),
        invocation_repo=RecordingInvocationRepository(log=log),
        event_bus=RecordingEventBus(log=log),
        approval_timeout=12.5,
    )
    return (
        service,
        service._invocation_repo,
        service._approval_service,
        service._event_bus,
        service._filesystem_policy_checker,
    )


@pytest.mark.asyncio
async def test_service_executes_allowed_tool() -> None:
    log: list[str] = []
    tool = RecordingTool(
        name="shell",
        result=ToolResult(success=True, output={"stdout": "ok"}, summary="ran shell"),
        log=log,
    )
    service, repo, approval_service, event_bus, _ = build_service(tool=tool, log=log)

    result = await service.execute_tool(
        session_id="ses_123",
        agent_id="agt_123",
        tool_name="shell",
        arguments={"command": "pwd"},
    )

    assert result.success is True
    assert result.output == {"stdout": "ok"}
    assert approval_service.request_calls == []
    assert len(repo.created) == 1
    assert repo.created[0].status == ToolStatus.PENDING
    assert [update["status"] for update in repo.updates] == [ToolStatus.RUNNING, ToolStatus.COMPLETED]
    assert isinstance(event_bus.events[0], ToolInvocationStartedEvent)
    assert isinstance(event_bus.events[1], ToolInvocationCompletedEvent)
    assert log == [
        "repo.create",
        "repo.update:running",
        "event.started",
        "tool.execute",
        "repo.update:completed",
        "event.completed",
    ]


@pytest.mark.asyncio
async def test_service_rejects_denied_tool() -> None:
    log: list[str] = []
    tool = RecordingTool(name="shell", log=log)
    service, repo, approval_service, event_bus, _ = build_service(
        tool=tool,
        tool_policy_action=PolicyAction.DENY,
        log=log,
    )

    result = await service.execute_tool(
        session_id="ses_123",
        agent_id="agt_123",
        tool_name="shell",
        arguments={"command": "pwd"},
    )

    assert result.success is False
    assert "denied" in result.error.lower()
    assert tool.calls == []
    assert approval_service.request_calls == []
    assert len(repo.created) == 1
    assert [update["status"] for update in repo.updates] == [ToolStatus.DENIED]
    assert event_bus.events == []


@pytest.mark.asyncio
async def test_service_fails_for_unknown_tool() -> None:
    log: list[str] = []
    service, repo, approval_service, event_bus, filesystem_policy_checker = build_service(
        tool=None,
        log=log,
    )

    result = await service.execute_tool(
        session_id="ses_123",
        agent_id="agt_123",
        tool_name="missing",
        arguments={"command": "pwd"},
    )

    assert result.success is False
    assert "unknown tool" in result.error.lower()
    assert repo.created == []
    assert repo.updates == []
    assert approval_service.request_calls == []
    assert approval_service.wait_calls == []
    assert event_bus.events == []
    assert filesystem_policy_checker.calls == []


@pytest.mark.asyncio
async def test_service_requests_approval_before_execution() -> None:
    log: list[str] = []
    tool = RecordingTool(name="shell", log=log)
    service, repo, approval_service, event_bus, _ = build_service(
        tool=tool,
        tool_policy_action=PolicyAction.REQUIRE_APPROVAL,
        approval_granted=True,
        log=log,
    )

    result = await service.execute_tool(
        session_id="ses_123",
        agent_id="agt_123",
        tool_name="shell",
        arguments={"command": "pwd"},
    )

    assert result.success is True
    assert len(approval_service.request_calls) == 1
    assert len(approval_service.wait_calls) == 1
    assert approval_service.wait_calls[0] == ("apr_test", 12.5)
    assert isinstance(event_bus.events[0], ApprovalRequestedEvent)
    assert isinstance(event_bus.events[1], ToolInvocationStartedEvent)
    assert isinstance(event_bus.events[2], ToolInvocationCompletedEvent)
    assert repo.updates[0]["status"] == ToolStatus.PENDING
    assert repo.updates[0]["approval_id"] == "apr_test"
    assert log == [
        "repo.create",
        "approval.request",
        "event.approval_requested",
        "repo.update:pending",
        "approval.wait",
        "repo.update:running",
        "event.started",
        "tool.execute",
        "repo.update:completed",
        "event.completed",
    ]


@pytest.mark.asyncio
async def test_service_stops_when_approval_denied() -> None:
    log: list[str] = []
    tool = RecordingTool(name="shell", log=log)
    service, repo, approval_service, event_bus, _ = build_service(
        tool=tool,
        tool_policy_action=PolicyAction.REQUIRE_APPROVAL,
        approval_granted=False,
        log=log,
    )

    result = await service.execute_tool(
        session_id="ses_123",
        agent_id="agt_123",
        tool_name="shell",
        arguments={"command": "pwd"},
    )

    assert result.success is False
    assert "approval" in result.error.lower()
    assert tool.calls == []
    assert len(approval_service.request_calls) == 1
    assert len(approval_service.wait_calls) == 1
    assert [update["status"] for update in repo.updates] == [ToolStatus.PENDING, ToolStatus.DENIED]
    assert len(event_bus.events) == 1
    assert isinstance(event_bus.events[0], ApprovalRequestedEvent)


@pytest.mark.asyncio
async def test_service_blocks_filesystem_operation_when_path_denied() -> None:
    log: list[str] = []
    tool = RecordingTool(name="filesystem", log=log)
    service, repo, approval_service, event_bus, filesystem_policy_checker = build_service(
        tool=tool,
        filesystem_policy_action=PolicyAction.DENY,
        log=log,
    )

    result = await service.execute_tool(
        session_id="ses_123",
        agent_id="agt_123",
        tool_name="filesystem",
        arguments={"operation": "write", "path": "/restricted/file.txt", "content": "x"},
    )

    assert result.success is False
    assert "filesystem" in result.error.lower()
    assert tool.calls == []
    assert approval_service.request_calls == []
    assert filesystem_policy_checker.calls == [
        ("/restricted/file.txt", FilesystemOperation.WRITE)
    ]
    assert len(repo.created) == 1
    assert [update["status"] for update in repo.updates] == [ToolStatus.DENIED]
    assert event_bus.events == []


@pytest.mark.asyncio
async def test_service_records_failure_when_tool_raises() -> None:
    log: list[str] = []
    tool = RecordingTool(name="shell", error=RuntimeError("boom"), log=log)
    service, repo, _, event_bus, _ = build_service(tool=tool, log=log)

    result = await service.execute_tool(
        session_id="ses_123",
        agent_id="agt_123",
        tool_name="shell",
        arguments={"command": "pwd"},
    )

    assert result.success is False
    assert "boom" in result.error
    assert [update["status"] for update in repo.updates] == [ToolStatus.RUNNING, ToolStatus.FAILED]
    assert isinstance(event_bus.events[0], ToolInvocationStartedEvent)
    assert isinstance(event_bus.events[1], ToolInvocationFailedEvent)
    assert log == [
        "repo.create",
        "repo.update:running",
        "event.started",
        "tool.execute",
        "repo.update:failed",
        "event.failed",
    ]
