"""Tests for TaskState enum and StateMachine ABC."""
import pytest
from system.orchestrator.state_machine import TaskState, StateMachine, Task


def test_task_state_count():
    # Spec heading says "17 states" but enumerates 18 including RETRY_PENDING.
    # We implement all 18 as listed in the spec's transition table.
    states = list(TaskState)
    assert len(states) == 18


def test_task_state_values():
    assert TaskState.NEW == "NEW"
    assert TaskState.DONE == "DONE"
    assert TaskState.BLOCKED == "BLOCKED"
    assert TaskState.RETRY_PENDING == "RETRY_PENDING"
    assert TaskState.QA_FAILED == "QA_FAILED"
    assert TaskState.READY_FOR_MERGE_REVIEW == "READY_FOR_MERGE_REVIEW"


def test_task_model_defaults():
    t = Task(task_id="BRQ-1", state=TaskState.NEW)
    assert t.rework_count == 0
    assert t.retry_count == 0
    assert t.failure_source is None
    assert t.branch is None


def test_state_machine_is_abstract():
    with pytest.raises(TypeError):
        StateMachine()
