"""Tests for breqy.tui.widgets.task_panel — TaskPanel widget."""
from __future__ import annotations

import pytest

from textual.app import App, ComposeResult
from textual.widgets import RichLog

from breqy.domain.enums import TaskStatus
from breqy.tui.constants import TASK_STATUS_ICONS
from breqy.tui.widgets.task_panel import TaskPanel


class TaskPanelApp(App[None]):
    """Minimal app that mounts a TaskPanel for testing."""

    def compose(self) -> ComposeResult:
        yield TaskPanel()


class TestTaskPanelCompose:
    """Test that TaskPanel mounts with a RichLog."""

    @pytest.mark.asyncio
    async def test_mounts_rich_log_widget(self) -> None:
        app = TaskPanelApp()
        async with app.run_test() as pilot:
            logs = app.query(RichLog)
            assert len(logs) == 1

    @pytest.mark.asyncio
    async def test_log_widget_property(self) -> None:
        app = TaskPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(TaskPanel)
            log = panel.log_widget
            assert isinstance(log, RichLog)


class TestTaskPanelEmptyState:
    """Test empty state displays placeholder text."""

    @pytest.mark.asyncio
    async def test_empty_state_shows_no_tasks(self) -> None:
        app = TaskPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(TaskPanel)
            await pilot.pause()
            # Empty state should show one line: "[dim]No tasks[/dim]"
            assert len(panel.log_widget.lines) == 1


class TestTaskPanelAddNewTask:
    """Test adding a new task shows PENDING with correct icon."""

    @pytest.mark.asyncio
    async def test_add_pending_task(self) -> None:
        app = TaskPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(TaskPanel)
            panel.update_task("tsk_001", title="Fix the bug", status=TaskStatus.PENDING)
            await pilot.pause()
            # Should have 1 line (the task), no empty-state line
            assert len(panel.log_widget.lines) == 1
            # Verify the task is tracked internally
            assert "tsk_001" in panel._tasks


class TestTaskPanelStatusIcons:
    """Test that each status renders the correct icon."""

    @pytest.mark.asyncio
    async def test_running_task_icon(self) -> None:
        app = TaskPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(TaskPanel)
            panel.update_task("tsk_001", title="Build project", status=TaskStatus.RUNNING)
            await pilot.pause()
            assert len(panel.log_widget.lines) == 1
            assert "tsk_001" in panel._tasks
            assert panel._tasks["tsk_001"]["status"] == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_completed_task_icon(self) -> None:
        app = TaskPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(TaskPanel)
            panel.update_task("tsk_001", title="Run tests", status=TaskStatus.COMPLETED)
            await pilot.pause()
            assert len(panel.log_widget.lines) == 1
            assert panel._tasks["tsk_001"]["status"] == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_failed_task_icon(self) -> None:
        app = TaskPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(TaskPanel)
            panel.update_task("tsk_001", title="Deploy", status=TaskStatus.FAILED)
            await pilot.pause()
            assert len(panel.log_widget.lines) == 1
            assert panel._tasks["tsk_001"]["status"] == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_cancelled_task_icon(self) -> None:
        app = TaskPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(TaskPanel)
            panel.update_task("tsk_001", title="Cleanup", status=TaskStatus.CANCELLED)
            await pilot.pause()
            assert len(panel.log_widget.lines) == 1
            assert panel._tasks["tsk_001"]["status"] == TaskStatus.CANCELLED


class TestTaskPanelStatusTransition:
    """Test updating a task status re-renders correctly."""

    @pytest.mark.asyncio
    async def test_update_pending_to_running(self) -> None:
        app = TaskPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(TaskPanel)
            panel.update_task("tsk_001", title="Fix the bug", status=TaskStatus.PENDING)
            await pilot.pause()
            assert panel._tasks["tsk_001"]["status"] == TaskStatus.PENDING

            panel.update_task("tsk_001", title="Fix the bug", status=TaskStatus.RUNNING)
            await pilot.pause()
            assert panel._tasks["tsk_001"]["status"] == TaskStatus.RUNNING
            # Still just one task line
            assert len(panel.log_widget.lines) == 1


class TestTaskPanelNestedTasks:
    """Test that tasks with parent_id are indented."""

    @pytest.mark.asyncio
    async def test_nested_task_indented(self) -> None:
        app = TaskPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(TaskPanel)
            panel.update_task("tsk_001", title="Parent task", status=TaskStatus.RUNNING)
            panel.update_task(
                "tsk_002",
                title="Child task",
                status=TaskStatus.PENDING,
                parent_id="tsk_001",
            )
            await pilot.pause()
            # Should show 2 lines (parent + child)
            assert len(panel.log_widget.lines) == 2
            # Child task should have parent_id tracked
            assert panel._tasks["tsk_002"]["parent_id"] == "tsk_001"


class TestTaskPanelMultipleTasks:
    """Test multiple tasks rendered in insertion order."""

    @pytest.mark.asyncio
    async def test_multiple_tasks_in_order(self) -> None:
        app = TaskPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(TaskPanel)
            panel.update_task("tsk_001", title="First task", status=TaskStatus.PENDING)
            panel.update_task("tsk_002", title="Second task", status=TaskStatus.RUNNING)
            panel.update_task("tsk_003", title="Third task", status=TaskStatus.COMPLETED)
            await pilot.pause()
            assert len(panel.log_widget.lines) == 3
            # Verify insertion order preserved
            task_ids = list(panel._tasks.keys())
            assert task_ids == ["tsk_001", "tsk_002", "tsk_003"]


class TestTaskPanelClear:
    """Test clear_tasks removes all tasks and shows empty state."""

    @pytest.mark.asyncio
    async def test_clear_tasks_returns_to_empty_state(self) -> None:
        app = TaskPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(TaskPanel)
            panel.update_task("tsk_001", title="Some task", status=TaskStatus.RUNNING)
            await pilot.pause()
            assert len(panel.log_widget.lines) == 1

            panel.clear_tasks()
            await pilot.pause()
            # Should show empty state again
            assert len(panel._tasks) == 0
            assert len(panel.log_widget.lines) == 1  # "[dim]No tasks[/dim]"
