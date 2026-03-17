import json
import pytest
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult
from system.orchestrator.agent_adapters.base import TaskContext
from system.orchestrator.agent_adapters.planner import PlannerAdapter
from system.orchestrator.agent_adapters.doer import DoerAdapter
from system.orchestrator.agent_adapters.checker import CheckerAdapter
from system.orchestrator.agent_adapters.tester import TesterAdapter
from system.orchestrator.agent_adapters.qa_automation import QaAutomationAdapter
from system.orchestrator.agent_adapters.lessons import LessonsAdapter


@pytest.fixture
def task():
    return TaskEnvelope(task_id="BRQ-1", title="Session resume", task_type="feature", component="backend")


@pytest.fixture
def ctx(task):
    return TaskContext(task=task, prior_artifacts={}, rework_count=0)


@pytest.fixture
def pass_result():
    return RunResult(status="completed", output='{"status": "pass"}', exit_code=0)


@pytest.fixture
def fail_result():
    return RunResult(
        status="completed",
        output=json.dumps({"status": "fail", "failure_source": "broken_implementation"}),
        exit_code=0,
    )


def test_planner_build_prompt_contains_task_id(task, ctx):
    adapter = PlannerAdapter()
    prompt = adapter.build_prompt(task, ctx)
    assert "BRQ-1" in prompt


def test_doer_build_prompt_contains_acceptance_criteria(ctx):
    task = TaskEnvelope(
        task_id="BRQ-1", title="t", task_type="feature", component="backend",
        acceptance_criteria=["It must work"],
    )
    adapter = DoerAdapter()
    prompt = adapter.build_prompt(task, TaskContext(task=task, prior_artifacts={}, rework_count=0))
    assert "It must work" in prompt


def test_checker_build_prompt_includes_diff(task, ctx):
    ctx_with_diff = ctx.model_copy(update={"prior_artifacts": {"git_diff": "diff --git..."}})
    adapter = CheckerAdapter()
    prompt = adapter.build_prompt(task, ctx_with_diff)
    assert "diff" in prompt.lower()


def test_qa_adapter_parse_fail_with_source(fail_result, task, ctx):
    adapter = QaAutomationAdapter()
    out = adapter.parse_output(fail_result)
    assert out.status == "fail"
    assert out.failure_source == "broken_implementation"


def test_generic_parse_output_pass(pass_result, task, ctx):
    for AdapterCls in (PlannerAdapter, DoerAdapter, CheckerAdapter, TesterAdapter, LessonsAdapter):
        adapter = AdapterCls()
        out = adapter.parse_output(pass_result)
        assert out.status == "pass"
