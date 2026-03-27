"""Unit tests for TaskManager — engine-owned task lifecycle."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio

from breqy.domain.enums import EventType, TaskStatus
from breqy.domain.errors import TaskTransitionError
from breqy.domain.events import TaskUpdatedEvent
from breqy.engine.event_bus import EventBus
from breqy.engine.task_manager import TaskManager
from breqy.storage.sqlite.task_repo import SqliteTaskRepository


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

# Session IDs used across tests — pre-seeded into the DB to satisfy FKs.
_SESSION_IDS = ("ses_test", "ses_a", "ses_x", "ses_empty")


@pytest.fixture()
def event_bus() -> EventBus:
    return EventBus()


@pytest_asyncio.fixture()
async def task_manager(db_connection, event_bus) -> TaskManager:
    # Seed session rows so tasks can reference them via FK.
    now = datetime.now(timezone.utc).isoformat()
    for sid in _SESSION_IDS:
        await db_connection.execute(
            "INSERT OR IGNORE INTO sessions "
            "(id, status, primary_agent_id, workspace_paths, created_at, updated_at) "
            "VALUES (?, 'active', 'breqy', '[]', ?, ?)",
            (sid, now, now),
        )
    await db_connection.commit()

    repo = SqliteTaskRepository(db_connection)
    return TaskManager(task_repo=repo, event_bus=event_bus)


# ------------------------------------------------------------------ #
# create_task
# ------------------------------------------------------------------ #


@pytest.mark.asyncio()
async def test_create_task(task_manager: TaskManager) -> None:
    task = await task_manager.create_task(session_id="ses_test", title="My task")

    assert task.session_id == "ses_test"
    assert task.title == "My task"
    assert task.status == TaskStatus.PENDING
    assert task.id.startswith("tsk_")


@pytest.mark.asyncio()
async def test_create_task_emits_event(
    task_manager: TaskManager, event_bus: EventBus
) -> None:
    captured: list[TaskUpdatedEvent] = []

    async def capture(e: TaskUpdatedEvent) -> None:
        captured.append(e)

    event_bus.subscribe(EventType.TASK_CREATED, capture)
    task = await task_manager.create_task(session_id="ses_test", title="My task")

    assert len(captured) == 1
    assert captured[0].task_id == task.id
    assert captured[0].status == TaskStatus.PENDING
    assert captured[0].event_type == EventType.TASK_CREATED


@pytest.mark.asyncio()
async def test_create_task_with_parent(task_manager: TaskManager) -> None:
    parent = await task_manager.create_task(session_id="ses_test", title="Parent")
    child = await task_manager.create_task(
        session_id="ses_test", title="Child", parent_id=parent.id
    )

    assert child.parent_id == parent.id
    persisted = await task_manager.get_task(child.id)
    assert persisted is not None
    assert persisted.parent_id == parent.id


# ------------------------------------------------------------------ #
# update_task_status — valid transitions
# ------------------------------------------------------------------ #


@pytest.mark.asyncio()
async def test_update_task_pending_to_running(task_manager: TaskManager) -> None:
    task = await task_manager.create_task(session_id="ses_test", title="T")
    updated = await task_manager.update_task_status(task.id, TaskStatus.RUNNING)

    assert updated.status == TaskStatus.RUNNING


@pytest.mark.asyncio()
async def test_update_task_running_to_completed(task_manager: TaskManager) -> None:
    task = await task_manager.create_task(session_id="ses_test", title="T")
    await task_manager.update_task_status(task.id, TaskStatus.RUNNING)
    updated = await task_manager.update_task_status(task.id, TaskStatus.COMPLETED)

    assert updated.status == TaskStatus.COMPLETED


@pytest.mark.asyncio()
async def test_update_task_running_to_failed(task_manager: TaskManager) -> None:
    task = await task_manager.create_task(session_id="ses_test", title="T")
    await task_manager.update_task_status(task.id, TaskStatus.RUNNING)
    updated = await task_manager.update_task_status(task.id, TaskStatus.FAILED)

    assert updated.status == TaskStatus.FAILED


@pytest.mark.asyncio()
async def test_update_task_running_to_cancelled(task_manager: TaskManager) -> None:
    task = await task_manager.create_task(session_id="ses_test", title="T")
    await task_manager.update_task_status(task.id, TaskStatus.RUNNING)
    updated = await task_manager.update_task_status(task.id, TaskStatus.CANCELLED)

    assert updated.status == TaskStatus.CANCELLED


@pytest.mark.asyncio()
async def test_update_task_pending_to_cancelled(task_manager: TaskManager) -> None:
    task = await task_manager.create_task(session_id="ses_test", title="T")
    updated = await task_manager.update_task_status(task.id, TaskStatus.CANCELLED)

    assert updated.status == TaskStatus.CANCELLED


# ------------------------------------------------------------------ #
# update_task_status — terminal states (no outgoing transitions)
# ------------------------------------------------------------------ #


@pytest.mark.asyncio()
async def test_update_task_completed_is_terminal(task_manager: TaskManager) -> None:
    task = await task_manager.create_task(session_id="ses_test", title="T")
    await task_manager.update_task_status(task.id, TaskStatus.RUNNING)
    await task_manager.update_task_status(task.id, TaskStatus.COMPLETED)

    with pytest.raises(TaskTransitionError):
        await task_manager.update_task_status(task.id, TaskStatus.RUNNING)


@pytest.mark.asyncio()
async def test_update_task_failed_is_terminal(task_manager: TaskManager) -> None:
    task = await task_manager.create_task(session_id="ses_test", title="T")
    await task_manager.update_task_status(task.id, TaskStatus.RUNNING)
    await task_manager.update_task_status(task.id, TaskStatus.FAILED)

    with pytest.raises(TaskTransitionError):
        await task_manager.update_task_status(task.id, TaskStatus.RUNNING)


@pytest.mark.asyncio()
async def test_update_task_cancelled_is_terminal(task_manager: TaskManager) -> None:
    task = await task_manager.create_task(session_id="ses_test", title="T")
    await task_manager.update_task_status(task.id, TaskStatus.CANCELLED)

    with pytest.raises(TaskTransitionError):
        await task_manager.update_task_status(task.id, TaskStatus.RUNNING)


# ------------------------------------------------------------------ #
# update_task_status — invalid transitions
# ------------------------------------------------------------------ #


@pytest.mark.asyncio()
async def test_update_task_invalid_transition(task_manager: TaskManager) -> None:
    task = await task_manager.create_task(session_id="ses_test", title="T")

    with pytest.raises(TaskTransitionError):
        await task_manager.update_task_status(task.id, TaskStatus.COMPLETED)


@pytest.mark.asyncio()
async def test_update_task_not_found(task_manager: TaskManager) -> None:
    with pytest.raises(ValueError, match="Task not found"):
        await task_manager.update_task_status("tsk_nonexistent", TaskStatus.RUNNING)


# ------------------------------------------------------------------ #
# update_task_status — event emission
# ------------------------------------------------------------------ #


@pytest.mark.asyncio()
async def test_update_task_emits_event(
    task_manager: TaskManager, event_bus: EventBus
) -> None:
    captured: list[TaskUpdatedEvent] = []

    async def capture(e: TaskUpdatedEvent) -> None:
        captured.append(e)

    event_bus.subscribe(EventType.TASK_UPDATED, capture)
    task = await task_manager.create_task(session_id="ses_test", title="T")
    await task_manager.update_task_status(task.id, TaskStatus.RUNNING)

    assert len(captured) == 1
    assert captured[0].task_id == task.id
    assert captured[0].status == TaskStatus.RUNNING
    assert captured[0].event_type == EventType.TASK_UPDATED


@pytest.mark.asyncio()
async def test_update_task_completed_emits_completed_event(
    task_manager: TaskManager, event_bus: EventBus
) -> None:
    captured: list[TaskUpdatedEvent] = []

    async def capture(e: TaskUpdatedEvent) -> None:
        captured.append(e)

    event_bus.subscribe(EventType.TASK_COMPLETED, capture)
    task = await task_manager.create_task(session_id="ses_test", title="T")
    await task_manager.update_task_status(task.id, TaskStatus.RUNNING)
    await task_manager.update_task_status(task.id, TaskStatus.COMPLETED)

    assert len(captured) == 1
    assert captured[0].task_id == task.id
    assert captured[0].status == TaskStatus.COMPLETED
    assert captured[0].event_type == EventType.TASK_COMPLETED


# ------------------------------------------------------------------ #
# cancel_session_tasks
# ------------------------------------------------------------------ #


@pytest.mark.asyncio()
async def test_cancel_session_tasks(task_manager: TaskManager) -> None:
    t1 = await task_manager.create_task(session_id="ses_a", title="Pending task")
    t2 = await task_manager.create_task(session_id="ses_a", title="Running task")
    await task_manager.update_task_status(t2.id, TaskStatus.RUNNING)
    t3 = await task_manager.create_task(session_id="ses_a", title="Completed task")
    await task_manager.update_task_status(t3.id, TaskStatus.RUNNING)
    await task_manager.update_task_status(t3.id, TaskStatus.COMPLETED)

    count = await task_manager.cancel_session_tasks("ses_a")

    assert count == 2
    tasks = await task_manager.list_tasks("ses_a")
    statuses = {t.id: t.status for t in tasks}
    assert statuses[t1.id] == TaskStatus.CANCELLED
    assert statuses[t2.id] == TaskStatus.CANCELLED
    assert statuses[t3.id] == TaskStatus.COMPLETED


@pytest.mark.asyncio()
async def test_cancel_session_tasks_empty(task_manager: TaskManager) -> None:
    count = await task_manager.cancel_session_tasks("ses_empty")

    assert count == 0


# ------------------------------------------------------------------ #
# list_tasks / get_task
# ------------------------------------------------------------------ #


@pytest.mark.asyncio()
async def test_list_tasks(task_manager: TaskManager) -> None:
    await task_manager.create_task(session_id="ses_x", title="A")
    await task_manager.create_task(session_id="ses_x", title="B")

    tasks = await task_manager.list_tasks("ses_x")

    assert len(tasks) == 2
    titles = {t.title for t in tasks}
    assert titles == {"A", "B"}


@pytest.mark.asyncio()
async def test_get_task(task_manager: TaskManager) -> None:
    created = await task_manager.create_task(session_id="ses_test", title="T")

    fetched = await task_manager.get_task(created.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.title == "T"


@pytest.mark.asyncio()
async def test_get_task_not_found(task_manager: TaskManager) -> None:
    result = await task_manager.get_task("tsk_nonexistent")

    assert result is None
