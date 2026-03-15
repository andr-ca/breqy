import pytest
from pydantic import ValidationError
from system.orchestrator.schemas.task_envelope import TaskEnvelope


def test_task_envelope_minimal():
    env = TaskEnvelope(
        task_id="BRQ-1",
        title="Test task",
        task_type="feature",
        component="backend",
    )
    assert env.task_id == "BRQ-1"
    assert env.dependencies == []
    assert env.acceptance_criteria == []


def test_task_envelope_full():
    env = TaskEnvelope(
        task_id="BRQ-144",
        title="Session resume flow",
        description="Allow resuming sessions after rate limit",
        task_type="feature",
        component="backend",
        dependencies=["BRQ-100", "BRQ-101"],
        acceptance_criteria=["Sessions persist across restarts"],
        test_hints=["Test with mock rate limit response"],
        priority="high",
        labels=["orchestrator:managed"],
        github_issue_number=144,
    )
    assert env.github_issue_number == 144
    assert len(env.dependencies) == 2


def test_task_envelope_requires_task_id():
    with pytest.raises(ValidationError):
        TaskEnvelope(title="No ID", task_type="feature", component="backend")


def test_task_envelope_valid_task_types():
    for t in ("feature", "bug", "refactor", "hotfix"):
        env = TaskEnvelope(task_id="BRQ-1", title="t", task_type=t, component="backend")
        assert env.task_type == t


def test_task_envelope_invalid_task_type():
    with pytest.raises(ValidationError):
        TaskEnvelope(task_id="BRQ-1", title="t", task_type="unknown", component="backend")
