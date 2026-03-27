"""Integration tests for task lifecycle through the engine stack.

Tests create → update → cancel flows with real SQLite persistence and
event emission through the daemon-composed engine.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from breqy.config.models import EngineConfig
from breqy.domain.enums import EventType, TaskStatus
from breqy.domain.errors import TaskTransitionError
from breqy.engine.daemon import EngineDaemon


@pytest.mark.asyncio
async def test_task_full_lifecycle_pending_to_completed(tmp_dir: Path) -> None:
    """Task goes PENDING → RUNNING → COMPLETED with events emitted."""
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

        # Start event writer to capture events
        session = await server.session_manager.create_session("agt_breqy")

        task = await server.task_manager.create_task(
            session.id, "Write integration tests", description="Phase 9 Task 12",
        )
        assert task.status == TaskStatus.PENDING

        running = await server.task_manager.update_task_status(task.id, TaskStatus.RUNNING)
        assert running.status == TaskStatus.RUNNING

        completed = await server.task_manager.update_task_status(task.id, TaskStatus.COMPLETED)
        assert completed.status == TaskStatus.COMPLETED

        # Verify persisted state
        stored = await server.task_manager.get_task(task.id)
        assert stored is not None
        assert stored.status == TaskStatus.COMPLETED
    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_task_lifecycle_pending_to_cancelled(tmp_dir: Path) -> None:
    """Task goes PENDING → CANCELLED."""
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
        task = await server.task_manager.create_task(session.id, "Cancelled task")

        cancelled = await server.task_manager.update_task_status(task.id, TaskStatus.CANCELLED)
        assert cancelled.status == TaskStatus.CANCELLED
    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_task_invalid_transition_raises_error(tmp_dir: Path) -> None:
    """Invalid task state transition raises TaskTransitionError."""
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
        task = await server.task_manager.create_task(session.id, "Test task")

        # PENDING → COMPLETED is invalid (must go through RUNNING)
        with pytest.raises(TaskTransitionError):
            await server.task_manager.update_task_status(task.id, TaskStatus.COMPLETED)
    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_cancel_session_tasks_cancels_all_non_terminal(tmp_dir: Path) -> None:
    """cancel_session_tasks cancels PENDING and RUNNING but not already COMPLETED."""
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

        t_pending = await server.task_manager.create_task(session.id, "pending")
        t_running = await server.task_manager.create_task(session.id, "running")
        await server.task_manager.update_task_status(t_running.id, TaskStatus.RUNNING)
        t_done = await server.task_manager.create_task(session.id, "done")
        await server.task_manager.update_task_status(t_done.id, TaskStatus.RUNNING)
        await server.task_manager.update_task_status(t_done.id, TaskStatus.COMPLETED)

        cancelled_count = await server.task_manager.cancel_session_tasks(session.id)
        assert cancelled_count == 2

        # Verify final states
        tasks = await server.task_manager.list_tasks(session.id)
        statuses = {t.title: t.status for t in tasks}
        assert statuses["pending"] == TaskStatus.CANCELLED
        assert statuses["running"] == TaskStatus.CANCELLED
        assert statuses["done"] == TaskStatus.COMPLETED
    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_task_events_persisted_in_event_store(tmp_dir: Path) -> None:
    """Task lifecycle emits events that are durably persisted."""
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
        task = await server.task_manager.create_task(session.id, "Tracked task")
        await server.task_manager.update_task_status(task.id, TaskStatus.RUNNING)
        await server.task_manager.update_task_status(task.id, TaskStatus.COMPLETED)

        # Give event writer a moment to flush
        import asyncio
        await asyncio.sleep(0.1)

        events = await server.event_writer._repo.list_by_session(session.id, limit=20)
        task_event_types = [
            e.event_type for e in events
            if e.event_type in (
                EventType.TASK_CREATED,
                EventType.TASK_UPDATED,
                EventType.TASK_COMPLETED,
            )
        ]
        assert task_event_types == [
            EventType.TASK_CREATED,
            EventType.TASK_UPDATED,
            EventType.TASK_COMPLETED,
        ]
    finally:
        await daemon.stop()
