"""Tests for breqy.domain.errors — domain exception hierarchy."""
from __future__ import annotations

import pytest


# --- TaskTransitionError ---


def test_task_transition_error_exists():
    from breqy.domain.errors import TaskTransitionError

    assert TaskTransitionError is not None


def test_task_transition_error_inherits_from_breqy_error():
    from breqy.domain.errors import BreqyError, TaskTransitionError

    assert issubclass(TaskTransitionError, BreqyError)


def test_task_transition_error_stores_attributes():
    from breqy.domain.errors import TaskTransitionError

    err = TaskTransitionError(
        task_id="task_123",
        current_status="completed",
        requested_status="running",
    )
    assert err.task_id == "task_123"
    assert err.current_status == "completed"
    assert err.requested_status == "running"


def test_task_transition_error_message_format():
    from breqy.domain.errors import TaskTransitionError

    err = TaskTransitionError(
        task_id="task_456",
        current_status="completed",
        requested_status="running",
    )
    assert "task_456" in str(err)
    assert "completed" in str(err)
    assert "running" in str(err)
    assert "Invalid task transition" in str(err)


def test_task_transition_error_is_catchable_as_breqy_error():
    from breqy.domain.errors import BreqyError, TaskTransitionError

    with pytest.raises(BreqyError):
        raise TaskTransitionError(
            task_id="task_789",
            current_status="cancelled",
            requested_status="running",
        )


def test_task_transition_error_message_contains_arrow():
    """The message should show the transition direction with '->'."""
    from breqy.domain.errors import TaskTransitionError

    err = TaskTransitionError(
        task_id="task_abc",
        current_status="failed",
        requested_status="completed",
    )
    assert "failed -> completed" in str(err)
