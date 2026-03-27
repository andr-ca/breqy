"""Engine server: composites all engine components and handles A2A routing."""
from __future__ import annotations

from typing import Any

import structlog

from breqy.a2a.envelope import Envelope
from breqy.a2a.server import A2AServer
from breqy.domain.enums import EventType, MessageRole
from breqy.domain.events import (
    AgentLifecycleEvent,
    AgentWorkRequestedEvent,
    ControlEvent,
    MessageSentEvent,
    PrivateMemoryOperationRequestedEvent,
    PrivateMemoryOperationResultEvent,
    ToolExecutionRequestedEvent,
    ToolExecutionResultEvent,
)
from breqy.domain.models import SessionContextBundle, StructuredErrorPayload, StructuredResultPayload
from breqy.domain.models import Message
from breqy.engine.agent_registry import AgentRegistry
from breqy.engine.agent_spawner import AgentSpawner
from breqy.engine.control_handler import ControlHandler
from breqy.engine.event_bus import EventBus
from breqy.engine.event_writer import EventWriter
from breqy.engine.session_manager import SessionManager
from breqy.engine.task_manager import TaskManager
from breqy.memory import InMemoryVectorIndex, MemoryService
from breqy.policy.approval import ApprovalService
from breqy.policy.evaluator import PolicyEvaluator
from breqy.policy.filesystem import FilesystemPolicyChecker
from breqy.storage.interfaces import (
    ApprovalRepository,
    EventRepository,
    MemoryRepository,
    MessageRepository,
    ParticipantRepository,
    SessionRepository,
    TaskRepository,
    ToolInvocationRepository,
)
from breqy.tools.executor import ToolResult
from breqy.tools import (
    FilesystemTool,
    MemoryPromoteTool,
    MemorySearchTool,
    MemoryWriteTool,
    ShellTool,
    ToolRegistry,
    ToolService,
)

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
        memory_repo: MemoryRepository | None = None,
        tool_invocation_repo: ToolInvocationRepository | None = None,
        tool_registry: ToolRegistry | None = None,
        policy_evaluator: PolicyEvaluator | None = None,
        filesystem_policy_checker: FilesystemPolicyChecker | None = None,
        approval_service: ApprovalService | None = None,
        participant_repo: ParticipantRepository | None = None,
    ) -> None:
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._participant_repo = participant_repo
        self.event_bus = EventBus()
        self.event_writer = EventWriter(event_repo)
        self.session_manager = SessionManager(
            session_repo,
            message_repo,
            participant_repo=participant_repo,
        )
        self.agent_registry = AgentRegistry()
        self.agent_spawner = AgentSpawner(engine_socket=socket_path)
        self.approval_service = approval_service or ApprovalService(approval_repo)
        self.task_manager = TaskManager(task_repo, self.event_bus)
        self.control_handler: ControlHandler | None = None
        if participant_repo is not None:
            self.control_handler = ControlHandler(
                session_manager=self.session_manager,
                task_manager=self.task_manager,
                agent_registry=self.agent_registry,
                agent_spawner=self.agent_spawner,
                participant_repo=participant_repo,
                a2a_server=None,  # type: ignore[arg-type]  # set after a2a_server creation
            )
        self.memory_service = self._build_memory_service(
            repository=memory_repo,
            policy_evaluator=policy_evaluator,
            approval_service=self.approval_service,
        )
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
            on_disconnect=self._handle_disconnect,
        )
        # Patch the a2a_server reference into control_handler now that it exists
        if self.control_handler is not None:
            self.control_handler._a2a_server = self.a2a_server

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

        if isinstance(event, AgentLifecycleEvent) and event.event_type == EventType.AGENT_CONNECTED:
            self.agent_registry.register(
                event.agent_id,
                client_id=client_id,
                session_id=event.session_id,
            )
            # Create participant record if participant_repo is configured
            if self._participant_repo is not None:
                await self.session_manager.add_participant(
                    event.session_id, event.agent_id,
                )

        if isinstance(event, ControlEvent):
            if self.control_handler is not None:
                await self.control_handler.handle_control(event)
                return
            # Fall through to generic publish+broadcast if no control handler

        if isinstance(event, ToolExecutionRequestedEvent):
            await self._handle_tool_execution_request(event)
            return

        if isinstance(event, PrivateMemoryOperationRequestedEvent):
            await self._route_private_memory_request(event)
            return

        if isinstance(event, MessageSentEvent) and event.role == MessageRole.USER:
            await self._handle_user_message(event)
            return

        if isinstance(event, MessageSentEvent):
            await self._handle_runtime_message(event, client_id=client_id)
            return

        await self.event_bus.publish(event)
        await self.a2a_server.broadcast(envelope, exclude_client=client_id)

    async def _handle_disconnect(self, client_id: str) -> None:
        # Look up agent info before unregistering so we have session_id
        info = self.agent_registry.get_by_client_id(client_id)
        self.agent_registry.unregister_by_client_id(client_id)
        # Mark participant as left if we have session context
        if info is not None and info.session_id and self._participant_repo is not None:
            await self.session_manager.remove_participant(
                info.session_id, info.agent_id,
            )

    async def _handle_user_message(self, event: MessageSentEvent) -> None:
        message = await self.session_manager.add_message(
            session_id=event.session_id,
            role=event.role,
            content=event.content,
            agent_id=event.agent_id or None,
        )
        await self.event_bus.publish(event)

        session = await self.session_manager.get_session(event.session_id)
        if session is None:
            return
        agent_info = self.agent_registry.get(session.primary_agent_id)
        if agent_info is None:
            return

        messages = await self.session_manager.get_messages(event.session_id)
        work_event = AgentWorkRequestedEvent(
            session_id=event.session_id,
            agent_id=session.primary_agent_id,
            correlation_id=message.id,
            message_id=message.id,
            user_message_content=event.content,
            session_context=SessionContextBundle(messages=messages),
            active_skill_ids=[],
        )
        await self.a2a_server.send_to(agent_info.client_id, Envelope.from_event(work_event))

    async def _handle_runtime_message(self, event: MessageSentEvent, *, client_id: str) -> None:
        message = Message(
            id=event.message_id,
            session_id=event.session_id,
            role=event.role,
            content=event.content,
            agent_id=event.agent_id or None,
        )
        await self._message_repo.create(message)
        await self._session_repo.update_timestamp(event.session_id)
        await self.event_bus.publish(event)
        await self.a2a_server.broadcast(Envelope.from_event(event), exclude_client=client_id)

    async def _handle_tool_execution_request(self, event: ToolExecutionRequestedEvent) -> None:
        result = await self.execute_tool(
            session_id=event.session_id,
            agent_id=event.agent_id,
            tool_name=event.tool_name,
            arguments=event.arguments,
        )
        agent_info = self.agent_registry.get(event.agent_id)
        if agent_info is None:
            return
        if result.success:
            response = ToolExecutionResultEvent(
                session_id=event.session_id,
                agent_id=event.agent_id,
                correlation_id=event.invocation_id,
                invocation_id=event.invocation_id,
                success_payload=StructuredResultPayload(
                    summary=result.summary,
                    content=result.output,
                ),
            )
        else:
            response = ToolExecutionResultEvent(
                session_id=event.session_id,
                agent_id=event.agent_id,
                correlation_id=event.invocation_id,
                invocation_id=event.invocation_id,
                failure_payload=StructuredErrorPayload(
                    message=result.error or "Tool execution failed",
                    details=result.output,
                ),
            )
        await self.a2a_server.send_to(agent_info.client_id, Envelope.from_event(response))

    async def _route_private_memory_request(self, event: PrivateMemoryOperationRequestedEvent) -> None:
        agent_info = self.agent_registry.get(event.agent_id)
        if agent_info is None:
            return
        await self.a2a_server.send_to(agent_info.client_id, Envelope.from_event(event))

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

    def _build_memory_service(
        self,
        *,
        repository: MemoryRepository | None,
        policy_evaluator: PolicyEvaluator | None,
        approval_service: ApprovalService,
    ) -> MemoryService | None:
        if repository is None:
            return None

        return MemoryService(
            repository=repository,
            vector_index=InMemoryVectorIndex(),
            policy_evaluator=policy_evaluator or PolicyEvaluator([]),
            approval_service=approval_service,
            event_bus=self.event_bus,
        )

    def _build_default_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(ShellTool())
        registry.register(FilesystemTool())
        if self.memory_service is not None:
            registry.register(
                MemorySearchTool(
                    memory_service=self.memory_service,
                )
            )
            registry.register(
                MemoryWriteTool(
                    memory_service=self.memory_service,
                )
            )
            registry.register(MemoryPromoteTool(memory_service=self.memory_service))
        return registry
