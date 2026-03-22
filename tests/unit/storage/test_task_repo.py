"""Tests for SQLite task repository."""

import pytest

from breqy.domain.enums import TaskStatus
from breqy.domain.models import Session, Task
from breqy.storage.sqlite.session_repo import SqliteSessionRepository
from breqy.storage.sqlite.task_repo import SqliteTaskRepository


@pytest.mark.asyncio
async def test_create_and_get_task(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    task_repo = SqliteTaskRepository(db_connection)
    task = Task(session_id=session.id, title="Install nginx")
    await task_repo.create(task)

    result = await task_repo.get(task.id)
    assert result is not None
    assert result.title == "Install nginx"
    assert result.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_get_nonexistent_task(db_connection) -> None:
    task_repo = SqliteTaskRepository(db_connection)
    result = await task_repo.get("tsk_nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_update_task_status(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    task_repo = SqliteTaskRepository(db_connection)
    task = Task(session_id=session.id, title="Install nginx")
    await task_repo.create(task)

    await task_repo.update_status(task.id, TaskStatus.COMPLETED)
    result = await task_repo.get(task.id)
    assert result is not None
    assert result.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_list_tasks_by_session(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    task_repo = SqliteTaskRepository(db_connection)
    await task_repo.create(Task(session_id=session.id, title="Task 1"))
    await task_repo.create(Task(session_id=session.id, title="Task 2"))

    tasks = await task_repo.list_by_session(session.id)
    assert len(tasks) == 2


@pytest.mark.asyncio
async def test_task_roundtrip_with_parent_and_agent(db_connection) -> None:
    session_repo = SqliteSessionRepository(db_connection)
    session = Session(primary_agent_id="agent_breqy")
    await session_repo.create(session)

    task_repo = SqliteTaskRepository(db_connection)
    parent = Task(session_id=session.id, title="Parent")
    child = Task(
        session_id=session.id,
        title="Child",
        parent_id=parent.id,
        agent_id="agent_breqy",
    )
    await task_repo.create(parent)
    await task_repo.create(child)

    result = await task_repo.get(child.id)
    assert result is not None
    assert result.parent_id == parent.id
    assert result.agent_id == "agent_breqy"
