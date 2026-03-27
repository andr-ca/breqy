"""Tests for ControlHandler — engine-side control event routing."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from breqy.domain.enums import EventType, SessionStatus
from breqy.domain.events import ControlEvent
from breqy.domain.models import Participant
from breqy.engine.agent_registry import AgentInfo, AgentRegistry
from breqy.engine.control_handler import ControlHandler


SESSION_ID = "ses_test"


@pytest.fixture
def session_manager():
    return AsyncMock()


@pytest.fixture
def task_manager():
    mock = AsyncMock()
    mock.cancel_session_tasks.return_value = 2
    return mock


@pytest.fixture
def agent_registry():
    return AgentRegistry()


@pytest.fixture
def agent_spawner():
    return MagicMock()


@pytest.fixture
def participant_repo():
    return AsyncMock()


@pytest.fixture
def a2a_server():
    return AsyncMock()


@pytest.fixture
def handler(
    session_manager,
    task_manager,
    agent_registry,
    agent_spawner,
    participant_repo,
    a2a_server,
):
    return ControlHandler(
        session_manager=session_manager,
        task_manager=task_manager,
        agent_registry=agent_registry,
        agent_spawner=agent_spawner,
        participant_repo=participant_repo,
        a2a_server=a2a_server,
    )


# ------------------------------------------------------------------ #
# CONTROL_STOP
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_stop_cancels_tasks(handler, task_manager):
    """CONTROL_STOP calls task_manager.cancel_session_tasks."""
    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_STOP,
    )
    await handler.handle_control(event)

    task_manager.cancel_session_tasks.assert_awaited_once_with(SESSION_ID)


@pytest.mark.asyncio
async def test_stop_forwards_to_agents(handler, agent_registry, a2a_server):
    """CONTROL_STOP forwards event to all agents in the session."""
    agent_registry.register("agent_1", client_id="cli_1", session_id=SESSION_ID)
    agent_registry.register("agent_2", client_id="cli_2", session_id=SESSION_ID)

    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_STOP,
    )
    await handler.handle_control(event)

    assert a2a_server.send_to.await_count == 2
    call_client_ids = {
        call.args[0] for call in a2a_server.send_to.await_args_list
    }
    assert call_client_ids == {"cli_1", "cli_2"}


@pytest.mark.asyncio
async def test_stop_no_agents(handler, task_manager, a2a_server):
    """CONTROL_STOP with no agents still cancels tasks, no error."""
    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_STOP,
    )
    await handler.handle_control(event)

    task_manager.cancel_session_tasks.assert_awaited_once_with(SESSION_ID)
    a2a_server.send_to.assert_not_awaited()


# ------------------------------------------------------------------ #
# CONTROL_STOP_AND_STEER
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_stop_and_steer_cancels_tasks(handler, task_manager):
    """CONTROL_STOP_AND_STEER calls cancel_session_tasks."""
    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_STOP_AND_STEER,
        new_direction="pivot to plan B",
    )
    await handler.handle_control(event)

    task_manager.cancel_session_tasks.assert_awaited_once_with(SESSION_ID)


@pytest.mark.asyncio
async def test_stop_and_steer_forwards_to_agents(
    handler, agent_registry, a2a_server
):
    """CONTROL_STOP_AND_STEER forwards event to agents."""
    agent_registry.register("agent_1", client_id="cli_1", session_id=SESSION_ID)
    agent_registry.register("agent_2", client_id="cli_2", session_id=SESSION_ID)

    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_STOP_AND_STEER,
        new_direction="pivot to plan B",
    )
    await handler.handle_control(event)

    assert a2a_server.send_to.await_count == 2


@pytest.mark.asyncio
async def test_stop_and_steer_with_direction(handler, agent_registry, a2a_server):
    """CONTROL_STOP_AND_STEER carries new_direction in the forwarded event."""
    agent_registry.register("agent_1", client_id="cli_1", session_id=SESSION_ID)

    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_STOP_AND_STEER,
        new_direction="new plan",
    )
    await handler.handle_control(event)

    # The envelope passed to send_to wraps the original event
    sent_envelope = a2a_server.send_to.await_args_list[0].args[1]
    reconstructed = sent_envelope.to_event()
    assert reconstructed.new_direction == "new plan"


# ------------------------------------------------------------------ #
# CONTROL_STEER
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_steer_forwards_to_agents(handler, agent_registry, a2a_server):
    """CONTROL_STEER forwards event to agents."""
    agent_registry.register("agent_1", client_id="cli_1", session_id=SESSION_ID)

    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_STEER,
        new_direction="refocus on tests",
    )
    await handler.handle_control(event)

    a2a_server.send_to.assert_awaited_once()


@pytest.mark.asyncio
async def test_steer_does_not_cancel_tasks(handler, task_manager):
    """CONTROL_STEER does NOT call cancel_session_tasks."""
    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_STEER,
        new_direction="refocus",
    )
    await handler.handle_control(event)

    task_manager.cancel_session_tasks.assert_not_awaited()


@pytest.mark.asyncio
async def test_steer_with_direction(handler, agent_registry, a2a_server):
    """CONTROL_STEER carries new_direction in the forwarded envelope."""
    agent_registry.register("agent_1", client_id="cli_1", session_id=SESSION_ID)

    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_STEER,
        new_direction="switch to debugging",
    )
    await handler.handle_control(event)

    sent_envelope = a2a_server.send_to.await_args_list[0].args[1]
    reconstructed = sent_envelope.to_event()
    assert reconstructed.new_direction == "switch to debugging"


# ------------------------------------------------------------------ #
# CONTROL_CIRCUIT_BREAK
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_circuit_break_force_kills_agents(handler, agent_spawner):
    """CONTROL_CIRCUIT_BREAK calls agent_spawner.force_kill_by_session."""
    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_CIRCUIT_BREAK,
    )
    await handler.handle_control(event)

    agent_spawner.force_kill_by_session.assert_called_once_with(SESSION_ID)


@pytest.mark.asyncio
async def test_circuit_break_cancels_tasks(handler, task_manager):
    """CONTROL_CIRCUIT_BREAK calls cancel_session_tasks."""
    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_CIRCUIT_BREAK,
    )
    await handler.handle_control(event)

    task_manager.cancel_session_tasks.assert_awaited_once_with(SESSION_ID)


@pytest.mark.asyncio
async def test_circuit_break_marks_participants_left(handler, participant_repo):
    """CONTROL_CIRCUIT_BREAK gets active participants and marks them as left."""
    p1 = Participant(session_id=SESSION_ID, agent_id="agent_1")
    p2 = Participant(session_id=SESSION_ID, agent_id="agent_2")
    participant_repo.get_active_by_session.return_value = [p1, p2]

    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_CIRCUIT_BREAK,
    )
    await handler.handle_control(event)

    participant_repo.get_active_by_session.assert_awaited_once_with(SESSION_ID)
    assert participant_repo.set_left_at.await_count == 2
    left_participant_ids = {
        call.args[0] for call in participant_repo.set_left_at.await_args_list
    }
    assert left_participant_ids == {p1.id, p2.id}


@pytest.mark.asyncio
async def test_circuit_break_sets_session_circuit_broken(handler, session_manager):
    """CONTROL_CIRCUIT_BREAK calls session_manager.circuit_break_session."""
    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_CIRCUIT_BREAK,
    )
    await handler.handle_control(event)

    session_manager.circuit_break_session.assert_awaited_once_with(SESSION_ID)


@pytest.mark.asyncio
async def test_circuit_break_unregisters_agents(handler, agent_registry):
    """CONTROL_CIRCUIT_BREAK unregisters all agents from the registry."""
    agent_registry.register("agent_1", client_id="cli_1", session_id=SESSION_ID)
    agent_registry.register("agent_2", client_id="cli_2", session_id=SESSION_ID)
    # Also register an agent for a different session — should NOT be removed
    agent_registry.register("agent_3", client_id="cli_3", session_id="ses_other")

    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_CIRCUIT_BREAK,
    )
    await handler.handle_control(event)

    # Session agents should be gone
    assert agent_registry.list_by_session(SESSION_ID) == []
    # Other session's agent should still be there
    assert len(agent_registry.list_by_session("ses_other")) == 1


@pytest.mark.asyncio
async def test_circuit_break_no_active_participants(handler, participant_repo):
    """CONTROL_CIRCUIT_BREAK with no active participants doesn't error."""
    participant_repo.get_active_by_session.return_value = []

    event = ControlEvent(
        session_id=SESSION_ID,
        event_type=EventType.CONTROL_CIRCUIT_BREAK,
    )
    await handler.handle_control(event)

    participant_repo.get_active_by_session.assert_awaited_once_with(SESSION_ID)
    participant_repo.set_left_at.assert_not_awaited()
