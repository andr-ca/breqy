"""Engine-side control event routing.

Dispatches incoming ``ControlEvent`` instances to the correct handler
based on the event type, coordinating SessionManager, TaskManager,
AgentRegistry, AgentSpawner, ParticipantRepository, and A2AServer.
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog

from breqy.a2a.envelope import Envelope
from breqy.a2a.server import A2AServer
from breqy.domain.enums import EventType
from breqy.domain.events import ControlEvent
from breqy.engine.agent_registry import AgentRegistry
from breqy.engine.agent_spawner import AgentSpawner
from breqy.engine.session_manager import SessionManager
from breqy.engine.task_manager import TaskManager
from breqy.storage.interfaces import ParticipantRepository

logger = structlog.get_logger(__name__)


class ControlHandler:
    """Routes control events to the appropriate engine-side actions."""

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        task_manager: TaskManager,
        agent_registry: AgentRegistry,
        agent_spawner: AgentSpawner,
        participant_repo: ParticipantRepository,
        a2a_server: A2AServer,
    ) -> None:
        self._session_manager = session_manager
        self._task_manager = task_manager
        self._agent_registry = agent_registry
        self._agent_spawner = agent_spawner
        self._participant_repo = participant_repo
        self._a2a_server = a2a_server

    # ------------------------------------------------------------------ #
    # Public dispatch
    # ------------------------------------------------------------------ #

    async def handle_control(self, event: ControlEvent) -> None:
        """Route a control event to the correct private handler."""
        handlers = {
            EventType.CONTROL_STOP: self._handle_stop,
            EventType.CONTROL_STOP_AND_STEER: self._handle_stop_and_steer,
            EventType.CONTROL_STEER: self._handle_steer,
            EventType.CONTROL_CIRCUIT_BREAK: self._handle_circuit_break,
        }
        handler = handlers.get(event.event_type)
        if handler is None:
            logger.warning(
                "Unknown control event type",
                event_type=event.event_type,
                session_id=event.session_id,
            )
            return
        await handler(event)

    # ------------------------------------------------------------------ #
    # Private handlers
    # ------------------------------------------------------------------ #

    async def _handle_stop(self, event: ControlEvent) -> None:
        """Cancel tasks and forward stop signal to all agents."""
        await self._task_manager.cancel_session_tasks(event.session_id)
        await self._forward_to_session_agents(event)
        logger.info(
            "Control stop processed",
            session_id=event.session_id,
        )

    async def _handle_stop_and_steer(self, event: ControlEvent) -> None:
        """Forward stop-and-steer to agents, then cancel tasks."""
        await self._forward_to_session_agents(event)
        await self._task_manager.cancel_session_tasks(event.session_id)
        logger.info(
            "Control stop-and-steer processed",
            session_id=event.session_id,
            new_direction=event.new_direction,
        )

    async def _handle_steer(self, event: ControlEvent) -> None:
        """Forward steer signal to agents — no task cancellation."""
        await self._forward_to_session_agents(event)
        logger.info(
            "Control steer processed",
            session_id=event.session_id,
            new_direction=event.new_direction,
        )

    async def _handle_circuit_break(self, event: ControlEvent) -> None:
        """Emergency termination: kill processes, cancel tasks, mark left."""
        session_id = event.session_id

        # 1. Force-kill all agent processes
        self._agent_spawner.force_kill_by_session(session_id)

        # 2. Cancel all non-terminal tasks
        await self._task_manager.cancel_session_tasks(session_id)

        # 3. Mark all active participants as left
        participants = await self._participant_repo.get_active_by_session(
            session_id
        )
        now = datetime.now(timezone.utc)
        for p in participants:
            await self._participant_repo.set_left_at(p.id, now)

        # 4. Mark session as CIRCUIT_BROKEN
        await self._session_manager.circuit_break_session(session_id)

        # 5. Unregister all agents from the registry
        agents = self._agent_registry.list_by_session(session_id)
        for agent in agents:
            self._agent_registry.unregister(agent.agent_id)

        logger.info(
            "Circuit break processed — emergency termination",
            session_id=session_id,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    async def _forward_to_session_agents(self, event: ControlEvent) -> None:
        """Forward a control event to all agents in the session."""
        agents = self._agent_registry.list_by_session(event.session_id)
        envelope = Envelope.from_event(event)
        for agent in agents:
            await self._a2a_server.send_to(agent.client_id, envelope)
