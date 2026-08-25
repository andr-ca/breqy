from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path as PathLib
from typing import Any

import structlog

from breqy.domain.enums import ApprovalStatus, PolicyAction, ToolStatus
from breqy.domain.events import (
    ApprovalRequestedEvent,
    ToolInvocationCompletedEvent,
    ToolInvocationFailedEvent,
    ToolInvocationStartedEvent,
)
from breqy.domain.models import ToolInvocation
from breqy.policy.approval import ApprovalService
from breqy.policy.evaluator import PolicyEvaluator
from breqy.policy.filesystem import FilesystemPolicyChecker
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
        session_manager: Any | None = None,
    ) -> None:
        self._registry = registry
        self._policy_evaluator = policy_evaluator
        self._filesystem_policy_checker = filesystem_policy_checker
        self._approval_service = approval_service
        self._invocation_repo = invocation_repo
        self._event_bus = event_bus
        self._approval_timeout = approval_timeout
        self._session_manager = session_manager

    async def close(self) -> None:
        for tool in self._registry.iter_tools():
            try:
                await tool.close()
            except Exception:
                logger.exception(
                    "Failed to close tool during ToolService shutdown",
                    tool_name=getattr(tool, "name", type(tool).__name__),
                )

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

        if self._session_manager is not None:
            workspace_violation = await self._check_workspace_boundary(session_id, invocation)
            if workspace_violation is not None:
                return workspace_violation

        if tool_name == "filesystem":
            denied_result = await self._check_filesystem_policy(invocation)
            if denied_result is not None:
                return denied_result

        approval_id: str | None = None
        approval_spec = tool.approval_request_spec(arguments)
        approval_description = (
            approval_spec.description
            if approval_spec is not None
            else self._build_approval_description(tool_name, arguments)
        )
        approval_grant_key = approval_spec.grant_key if approval_spec is not None else ""
        if decision.action == PolicyAction.REQUIRE_APPROVAL:
            await self._approval_service.ensure_grants_loaded(session_id)
            if not self._approval_service.has_grant(session_id, approval_grant_key):
                approval_id = await self._approval_service.request_approval(
                    session_id=session_id,
                    agent_id=agent_id,
                    tool_invocation_id=invocation.id,
                    description=approval_description,
                    grant_key=approval_grant_key,
                )
                await self._event_bus.publish(
                    ApprovalRequestedEvent(
                        session_id=session_id,
                        agent_id=agent_id,
                        approval_id=approval_id,
                        invocation_id=invocation.id,
                        description=approval_description,
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

                approval_status = await self._approval_service.wait_for_decision(
                    approval_id,
                    timeout=self._approval_timeout,
                )
                if approval_status == ApprovalStatus.DENIED:
                    return await self._finalize_denied(
                        invocation=invocation,
                        error=f"Approval denied for tool '{tool_name}'",
                        summary="Tool execution denied during approval",
                        approval_id=approval_id,
                    )
                if approval_status == ApprovalStatus.EXPIRED:
                    return await self._finalize_failed(
                        invocation=invocation,
                        error=f"Approval timed out for tool '{tool_name}'",
                        summary="Tool execution timed out waiting for approval",
                        approval_id=approval_id,
                    )

        started_at = datetime.now(UTC)
        await self._invocation_repo.update_result(
            invocation_id=invocation.id,
            status=ToolStatus.RUNNING,
            result=None,
            error="",
            summary="Tool execution started",
            approval_id=approval_id,
            started_at=started_at,
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
            execution_arguments = dict(arguments)
            execution_arguments["_execution_context"] = {
                "session_id": session_id,
                "agent_id": agent_id,
            }
            result = await tool.execute(execution_arguments)
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
                result=result.output,
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

    async def _check_workspace_boundary(
        self, session_id: str, invocation: ToolInvocation
    ) -> ToolResult | None:
        """Check if the tool's target path is within the session's workspace.

        Returns None if the path is allowed, or a denied ToolResult if blocked.
        Only applies when:
        1. Session has workspace_paths configured (non-empty)
        2. Tool arguments include a 'path' key

        If workspace_paths is empty, no restriction is applied (backward-compatible).
        """
        path = invocation.arguments.get("path")
        if not isinstance(path, str):
            return None

        session_manager = self._session_manager
        if session_manager is None:
            return None

        try:
            workspace_paths = await session_manager.get_workspace_paths(session_id)
        except (OSError, RuntimeError, LookupError, ValueError):
            # If session not found or any error, skip workspace check
            return None

        if not workspace_paths:
            return None  # No workspace restriction

        # Resolve the target path to absolute
        try:
            resolved = str(PathLib(path).resolve())
        except (OSError, ValueError):
            return await self._finalize_denied(
                invocation=invocation,
                error=f"Invalid path: {path}",
                summary="Path could not be resolved",
            )

        # Check if resolved path is inside any workspace path
        for ws_path in workspace_paths:
            try:
                ws_resolved = str(PathLib(ws_path).resolve())
            except (OSError, ValueError):
                continue
            if resolved == ws_resolved or resolved.startswith(ws_resolved + "/"):
                return None  # Path is inside this workspace

        return await self._finalize_denied(
            invocation=invocation,
            error=f"Path '{path}' is outside session workspace boundaries",
            summary="Workspace boundary violation",
        )

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
        result: dict[str, Any] | None = None,
        approval_id: str | None = None,
    ) -> ToolResult:
        await self._invocation_repo.update_result(
            invocation_id=invocation.id,
            status=ToolStatus.FAILED,
            result=result,
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
