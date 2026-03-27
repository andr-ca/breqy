"""Engine-owned task lifecycle management."""
from __future__ import annotations

import structlog

from breqy.domain.enums import EventType, TaskStatus
from breqy.domain.errors import TaskTransitionError
from breqy.domain.events import TaskUpdatedEvent
from breqy.domain.models import Task
from breqy.engine.event_bus import EventBus
from breqy.storage.interfaces import TaskRepository

logger = structlog.get_logger(__name__)


class TaskManager:
    """Owns the task lifecycle in the engine.

    Validates state transitions, persists via ``TaskRepository``,
    and emits ``TaskUpdatedEvent`` on every state change via ``EventBus``.
    """

    VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
        TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
        TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    }

    def __init__(self, task_repo: TaskRepository, event_bus: EventBus) -> None:
        self._tasks = task_repo
        self._bus = event_bus

    async def create_task(
        self,
        session_id: str,
        title: str,
        description: str = "",
        parent_id: str | None = None,
        agent_id: str | None = None,
    ) -> Task:
        """Create a new task in PENDING status."""
        task = Task(
            session_id=session_id,
            title=title,
            description=description,
            parent_id=parent_id,
            agent_id=agent_id,
        )
        await self._tasks.create(task)
        await self._bus.publish(
            TaskUpdatedEvent(
                session_id=session_id,
                task_id=task.id,
                title=title,
                status=TaskStatus.PENDING,
                event_type=EventType.TASK_CREATED,
            )
        )
        logger.info(
            "task_created",
            task_id=task.id,
            session_id=session_id,
            title=title,
        )
        return task

    async def update_task_status(self, task_id: str, new_status: TaskStatus) -> Task:
        """Transition a task to *new_status*, validating the transition."""
        task = await self._tasks.get(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")

        allowed = self.VALID_TRANSITIONS.get(task.status, set())
        if new_status not in allowed:
            raise TaskTransitionError(task_id, task.status.value, new_status.value)

        await self._tasks.update_status(task_id, new_status)

        if new_status == TaskStatus.COMPLETED:
            event_type = EventType.TASK_COMPLETED
        else:
            event_type = EventType.TASK_UPDATED

        await self._bus.publish(
            TaskUpdatedEvent(
                session_id=task.session_id,
                task_id=task_id,
                title=task.title,
                status=new_status,
                event_type=event_type,
            )
        )
        logger.info(
            "task_status_updated",
            task_id=task_id,
            old_status=task.status.value,
            new_status=new_status.value,
        )
        return task.model_copy(update={"status": new_status})

    async def cancel_session_tasks(self, session_id: str) -> int:
        """Cancel all non-terminal tasks for a session. Returns count cancelled."""
        tasks = await self._tasks.list_by_session(session_id)
        cancelled = 0
        for task in tasks:
            if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                await self.update_task_status(task.id, TaskStatus.CANCELLED)
                cancelled += 1
        logger.info(
            "session_tasks_cancelled",
            session_id=session_id,
            cancelled_count=cancelled,
        )
        return cancelled

    async def list_tasks(self, session_id: str) -> list[Task]:
        """Return all tasks for a session."""
        return await self._tasks.list_by_session(session_id)

    async def get_task(self, task_id: str) -> Task | None:
        """Return a single task by ID, or None."""
        return await self._tasks.get(task_id)
