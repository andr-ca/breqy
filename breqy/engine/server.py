"""Engine server: composites all engine components and handles A2A routing."""
from __future__ import annotations

from typing import Any

import structlog

from breqy.a2a.envelope import Envelope
from breqy.a2a.server import A2AServer
from breqy.engine.agent_registry import AgentRegistry
from breqy.engine.agent_spawner import AgentSpawner
from breqy.engine.event_bus import EventBus
from breqy.engine.event_writer import EventWriter
from breqy.engine.session_manager import SessionManager
from breqy.policy.approval import ApprovalService
from breqy.policy.evaluator import PolicyEvaluator
from breqy.policy.filesystem import FilesystemPolicyChecker
from breqy.storage.interfaces import (
    ApprovalRepository,
    EventRepository,
    MessageRepository,
    SessionRepository,
    TaskRepository,
    ToolInvocationRepository,
)
from breqy.tools.executor import ToolResult
from breqy.tools import FilesystemTool, ShellTool, ToolRegistry, ToolService

logger = structlog.get_logger(__name__)


class EngineServer:
    """Composes all engine subsystems and routes A2A traffic."""

    def __init__(
        self,
        socket_path: str,
        session_repo: SessionRepository,
        message_repo: MessageRepository,
        event_repo: EventRepository,
        task_repo: TaskRepository,
        approval_repo: ApprovalRepository,
        tool_invocation_repo: ToolInvocationRepository | None = None,
        tool_registry: ToolRegistry | None = None,
        policy_evaluator: PolicyEvaluator | None = None,
        filesystem_policy_checker: FilesystemPolicyChecker | None = None,
        approval_service: ApprovalService | None = None,
    ) -> None:
        self.event_bus = EventBus()
        self.event_writer = EventWriter(event_repo)
        self.session_manager = SessionManager(session_repo, message_repo)
        # TODO(phase-6): agent_registry is scaffolded here for future agent
        # registration/lookup — not yet wired into _handle_envelope routing.
        self.agent_registry = AgentRegistry()
        self.agent_spawner = AgentSpawner(engine_socket=socket_path)
        # TODO(phase-6): approval_service is scaffolded here for future
        # human-approval flow — not yet consulted in _handle_envelope.
        self.approval_service = approval_service or ApprovalService(approval_repo)
        self.tool_service = self._build_tool_service(
            approval_service=self.approval_service,
            tool_invocation_repo=tool_invocation_repo,
            tool_registry=tool_registry,
            policy_evaluator=policy_evaluator,
            filesystem_policy_checker=filesystem_policy_checker,
        )
        self.a2a_server = A2AServer(
            socket_path=socket_path,
            on_envelope=self._handle_envelope,
        )

    async def start(self) -> None:
        """Start all subsystems."""
        await self.event_writer.start()
        await self.a2a_server.start()
        # Wire event writer to receive all published events
        self.event_bus.subscribe_all(self.event_writer.write)
        logger.info("Engine server started")

    async def stop(self) -> None:
        """Stop all subsystems cleanly."""
        self.agent_spawner.kill_all()
        await self.a2a_server.stop()
        await self.event_writer.stop()
        logger.info("Engine server stopped")

    async def _handle_envelope(self, envelope: Envelope, client_id: str) -> None:
        """Route incoming A2A envelopes from agents/TUI."""
        event = envelope.to_event()
        await self.event_bus.publish(event)
        await self.a2a_server.broadcast(envelope, exclude_client=client_id)

    async def execute_tool(
        self,
        session_id: str,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Execute a tool through the engine-composed tool service."""
        if self.tool_service is None:
            raise RuntimeError("Tool service is not configured")
        return await self.tool_service.execute_tool(
            session_id=session_id,
            agent_id=agent_id,
            tool_name=tool_name,
            arguments=arguments,
        )

    def _build_tool_service(
        self,
        *,
        approval_service: ApprovalService,
        tool_invocation_repo: ToolInvocationRepository | None,
        tool_registry: ToolRegistry | None,
        policy_evaluator: PolicyEvaluator | None,
        filesystem_policy_checker: FilesystemPolicyChecker | None,
    ) -> ToolService | None:
        if tool_invocation_repo is None:
            return None

        registry = tool_registry or self._build_default_tool_registry()
        return ToolService(
            registry=registry,
            policy_evaluator=policy_evaluator or PolicyEvaluator([]),
            filesystem_policy_checker=filesystem_policy_checker or FilesystemPolicyChecker([]),
            approval_service=approval_service,
            invocation_repo=tool_invocation_repo,
            event_bus=self.event_bus,
        )

    @staticmethod
    def _build_default_tool_registry() -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(ShellTool())
        registry.register(FilesystemTool())
        return registry
