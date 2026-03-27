"""Integration tests for control signal flow through the engine stack.

Tests the full path: ControlEvent envelope → EngineServer → ControlHandler →
SessionManager / TaskManager / AgentRegistry / AgentSpawner.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from breqy.config.models import EngineConfig
from breqy.domain.enums import EventType, SessionStatus, TaskStatus
from breqy.domain.events import ControlEvent
from breqy.engine.daemon import EngineDaemon


@pytest.mark.asyncio
async def test_control_stop_cancels_session_tasks(tmp_dir: Path) -> None:
    """CONTROL_STOP cancels all pending/running tasks for the session."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()
    try:
        assert daemon.server is not None
        server = daemon.server

        session = await server.session_manager.create_session("agt_breqy")

        # Create tasks in various states
        task1 = await server.task_manager.create_task(session.id, "task-pending")
        task2 = await server.task_manager.create_task(session.id, "task-running")
        await server.task_manager.update_task_status(task2.id, TaskStatus.RUNNING)

        # Issue control stop
        await server.control_handler.handle_control(
            ControlEvent(
                session_id=session.id,
                event_type=EventType.CONTROL_STOP,
            )
        )

        # Both tasks should be cancelled
        t1 = await server.task_manager.get_task(task1.id)
        t2 = await server.task_manager.get_task(task2.id)
        assert t1.status == TaskStatus.CANCELLED
        assert t2.status == TaskStatus.CANCELLED
    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_circuit_break_marks_session_and_cancels_tasks(tmp_dir: Path) -> None:
    """CIRCUIT_BREAK marks session as CIRCUIT_BROKEN and cancels all tasks."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()
    try:
        assert daemon.server is not None
        server = daemon.server

        session = await server.session_manager.create_session("agt_breqy")
        task = await server.task_manager.create_task(session.id, "task-running")
        await server.task_manager.update_task_status(task.id, TaskStatus.RUNNING)

        # Add a participant
        await server.session_manager.add_participant(session.id, "agt_breqy")

        # Issue circuit break
        await server.control_handler.handle_control(
            ControlEvent(
                session_id=session.id,
                event_type=EventType.CONTROL_CIRCUIT_BREAK,
            )
        )

        # Session is circuit-broken
        updated_session = await server.session_manager.get_session(session.id)
        assert updated_session.status == SessionStatus.CIRCUIT_BROKEN

        # Task is cancelled
        updated_task = await server.task_manager.get_task(task.id)
        assert updated_task.status == TaskStatus.CANCELLED

        # No active participants remain
        participants = await server.session_manager.get_session_participants(session.id)
        assert len(participants) == 0
    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_control_steer_does_not_cancel_tasks(tmp_dir: Path) -> None:
    """CONTROL_STEER forwards direction but does NOT cancel tasks."""
    config = EngineConfig(
        socket_path=str(tmp_dir / "engine.sock"),
        db_path=str(tmp_dir / "test.db"),
        data_dir=str(tmp_dir),
    )
    daemon = EngineDaemon(config)
    await daemon.start()
    try:
        assert daemon.server is not None
        server = daemon.server

        session = await server.session_manager.create_session("agt_breqy")
        task = await server.task_manager.create_task(session.id, "task-running")
        await server.task_manager.update_task_status(task.id, TaskStatus.RUNNING)

        await server.control_handler.handle_control(
            ControlEvent(
                session_id=session.id,
                event_type=EventType.CONTROL_STEER,
                new_direction="Focus on unit tests instead",
            )
        )

        # Task should still be running
        updated_task = await server.task_manager.get_task(task.id)
        assert updated_task.status == TaskStatus.RUNNING
    finally:
        await daemon.stop()
