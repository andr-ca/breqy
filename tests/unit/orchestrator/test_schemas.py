"""Tests for orchestrator schema models."""
from __future__ import annotations

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


# --- RunResult / RunContext ---
from pathlib import Path

from system.orchestrator.schemas.run_result import RunContext, RunResult


def test_run_result_completed():
    r = RunResult(status="completed", output="done", exit_code=0)
    assert r.session_id is None
    assert r.artifacts_written == []


def test_run_result_rate_limited():
    r = RunResult(status="rate_limited", output="", exit_code=1, session_id="sid-abc")
    assert r.status == "rate_limited"
    assert r.session_id == "sid-abc"


def test_run_result_invalid_status():
    with pytest.raises(ValidationError):
        RunResult(status="unknown", output="", exit_code=0)


def test_run_context_defaults():
    ctx = RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))
    assert ctx.session_id is None
    assert ctx.extra_env == {}


def test_run_context_extra_env_independent():
    ctx1 = RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))
    ctx2 = RunContext(task_id="BRQ-2", role="doer", work_dir=Path("/tmp"))
    ctx1.extra_env["KEY"] = "val"
    assert "KEY" not in ctx2.extra_env


# --- Artifact schemas ---
from system.orchestrator.schemas.artifacts import (
    LessonsArtifact,
    MergeReadinessArtifact,
    ParsedOutput,
    QaArtifact,
    ReviewArtifact,
    TestArtifact,
)


def test_parsed_output_pass():
    p = ParsedOutput(status="pass", artifact_paths=["ai-artifacts/BRQ-1/doer-report.json"])
    assert p.failure_source is None
    assert p.notes == ""


def test_parsed_output_fail_with_source():
    p = ParsedOutput(
        status="fail",
        artifact_paths=[],
        failure_source="broken_implementation",
        notes="Tests failing",
    )
    assert p.failure_source == "broken_implementation"


def test_parsed_output_invalid_status():
    with pytest.raises(ValidationError):
        ParsedOutput(status="maybe", artifact_paths=[])


def test_review_artifact():
    r = ReviewArtifact(status="pass", findings=[], summary="LGTM")
    assert r.status == "pass"


def test_test_artifact():
    t = TestArtifact(status="fail", tests_run=10, tests_failed=2)
    assert t.tests_failed == 2


def test_qa_artifact_failure_source():
    q = QaArtifact(status="fail", failure_source="broken_automation")
    assert q.failure_source == "broken_automation"


def test_lessons_artifact():
    la = LessonsArtifact(task_id="BRQ-1", lessons=["Use mocks carefully"])
    assert la.instruction_update_proposed is False


def test_merge_readiness_artifact_pass():
    m = MergeReadinessArtifact(
        task_id="BRQ-1",
        checked_at="2026-03-14T14:00:00Z",
        artifacts_present=["task-envelope", "doer-report"],
        branch="feat/BRQ-1-test",
        merge_target="dev",
        ci_conclusion="success",
        branch_is_current=True,
        verdict="pass",
    )
    assert m.verdict == "pass"
