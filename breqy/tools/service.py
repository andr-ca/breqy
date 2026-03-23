from __future__ import annotations

from typing import Any

import structlog

from breqy.domain.enums import PolicyAction, ToolStatus
from breqy.domain.events import (
    ApprovalRequestedEvent,
    ToolInvocationCompletedEvent,
    ToolInvocationFailedEvent,
    ToolInvocationStartedEvent,
)
from breqy.domain.models import ToolInvocation
from breqy.policy.filesystem import FilesystemPolicyChecker
from breqy.policy.approval import ApprovalService
from breqy.policy.evaluator import PolicyEvaluator
from breqy.storage.interfaces import ToolInvocationRepository
from breqy.tools.executor import ToolResult
from breqy.tools.filesystem import derive_operations
from breqy.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


class ToolService:
    def __init__(
        self,
        registry: ToolRegistry,
        policy_evaluator: PolicyEvaluator,
        filesystem_policy_checker: FilesystemPolicyChecker,
        approval_service: ApprovalService,
        invocation_repo: ToolInvocationRepository,
        event_bus: Any,
        approval_timeout: float = 300.0,
    ) -> None:
        self._registry = registry
        self._policy_evaluator = policy_evaluator
        self._filesystem_policy_checker = filesystem_policy_checker
        self._approval_service = approval_service
        self._invocation_repo = invocation_repo
        self._event_bus = event_bus
        self._approval_timeout = approval_timeout

    async def execute_tool(
        self,
        session_id: str,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        tool = self._registry.get(tool_name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
                summary=f"Failed to resolve tool {tool_name}",
            )

        invocation = ToolInvocation(
            session_id=session_id,
            agent_id=agent_id,
            tool_name=tool_name,
            arguments=arguments,
            status=ToolStatus.PENDING,
        )
        await self._invocation_repo.create(invocation)

        decision = self._policy_evaluator.evaluate(
            resource=f"tool:{tool_name}",
            agent_id=agent_id,
            session_id=session_id,
        )
        if decision.action == PolicyAction.DENY:
            return await self._finalize_denied(
                invocation=invocation,
                error=f"Policy denied tool '{tool_name}'",
                summary="Tool execution denied by policy",
            )

        if tool_name == "filesystem":
            denied_result = await self._check_filesystem_policy(invocation)
            if denied_result is not None:
                return denied_result

        approval_id: str | None = None
        if decision.action == PolicyAction.REQUIRE_APPROVAL:
            approval_id = await self._approval_service.request_approval(
                session_id=session_id,
                agent_id=agent_id,
                tool_invocation_id=invocation.id,
                description=self._build_approval_description(tool_name, arguments),
            )
            await self._event_bus.publish(
                ApprovalRequestedEvent(
                    session_id=session_id,
                    agent_id=agent_id,
                    approval_id=approval_id,
                    invocation_id=invocation.id,
                    description=self._build_approval_description(tool_name, arguments),
                )
            )
            await self._invocation_repo.update_result(
                invocation_id=invocation.id,
                status=ToolStatus.PENDING,
                result=None,
                error="",
                summary="Waiting for approval",
                approval_id=approval_id,
            )

            approved = await self._approval_service.wait_for_decision(
                approval_id,
                timeout=self._approval_timeout,
            )
            if not approved:
                return await self._finalize_denied(
                    invocation=invocation,
                    error=f"Approval denied for tool '{tool_name}'",
                    summary="Tool execution denied during approval",
                    approval_id=approval_id,
                )

        await self._invocation_repo.update_result(
            invocation_id=invocation.id,
            status=ToolStatus.RUNNING,
            result=None,
            error="",
            summary="Tool execution started",
            approval_id=approval_id,
        )
        await self._event_bus.publish(
            ToolInvocationStartedEvent(
                session_id=session_id,
                agent_id=agent_id,
                invocation_id=invocation.id,
                tool_name=tool_name,
                arguments=arguments,
                summary="Tool execution started",
            )
        )

        try:
            result = await tool.execute(arguments)
        except Exception as exc:
            logger.exception(
                "Tool execution raised",
                session_id=session_id,
                agent_id=agent_id,
                tool_name=tool_name,
                invocation_id=invocation.id,
            )
            return await self._finalize_failed(
                invocation=invocation,
                error=str(exc),
                summary=f"Tool {tool_name} raised an exception",
                approval_id=approval_id,
            )

        if not result.success:
            return await self._finalize_failed(
                invocation=invocation,
                error=result.error or f"Tool execution failed: {tool_name}",
                summary=result.summary,
                approval_id=approval_id,
            )

        await self._invocation_repo.update_result(
            invocation_id=invocation.id,
            status=ToolStatus.COMPLETED,
            result=result.output,
            error="",
            summary=result.summary,
            approval_id=approval_id,
        )
        await self._event_bus.publish(
            ToolInvocationCompletedEvent(
                session_id=session_id,
                agent_id=agent_id,
                invocation_id=invocation.id,
                tool_name=tool_name,
                status=ToolStatus.COMPLETED,
                result=result.output,
                summary=result.summary,
            )
        )
        return result

    async def _check_filesystem_policy(self, invocation: ToolInvocation) -> ToolResult | None:
        path = invocation.arguments.get("path")
        if not isinstance(path, str):
            return None

        for operation in derive_operations(invocation.arguments):
            decision = self._filesystem_policy_checker.check(path, operation)
            if decision == PolicyAction.DENY:
                return await self._finalize_denied(
                    invocation=invocation,
                    error=f"Filesystem policy denied path '{path}'",
                    summary="Filesystem operation denied by policy",
                )

        return None

    async def _finalize_denied(
        self,
        invocation: ToolInvocation,
        error: str,
        summary: str,
        approval_id: str | None = None,
    ) -> ToolResult:
        await self._invocation_repo.update_result(
            invocation_id=invocation.id,
            status=ToolStatus.DENIED,
            result=None,
            error=error,
            summary=summary,
            approval_id=approval_id,
        )
        return ToolResult(success=False, error=error, summary=summary)

    async def _finalize_failed(
        self,
        invocation: ToolInvocation,
        error: str,
        summary: str,
        approval_id: str | None = None,
    ) -> ToolResult:
        await self._invocation_repo.update_result(
            invocation_id=invocation.id,
            status=ToolStatus.FAILED,
            result=None,
            error=error,
            summary=summary,
            approval_id=approval_id,
        )
        await self._event_bus.publish(
            ToolInvocationFailedEvent(
                session_id=invocation.session_id,
                agent_id=invocation.agent_id,
                invocation_id=invocation.id,
                tool_name=invocation.tool_name,
                error=error,
            )
        )
        return ToolResult(success=False, error=error, summary=summary)

    @staticmethod
    def _build_approval_description(tool_name: str, arguments: dict[str, Any]) -> str:
        return f"Execute tool '{tool_name}' with arguments {arguments}"
