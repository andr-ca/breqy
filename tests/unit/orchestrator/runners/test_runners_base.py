import pytest
from pathlib import Path
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult


def test_agent_runner_is_abstract():
    with pytest.raises(TypeError):
        AgentRunner()


def test_runner_interface():
    class MyRunner(AgentRunner):
        def run(self, prompt: str, context: RunContext) -> RunResult:
            return RunResult(status="completed", output="ok", exit_code=0)

    runner = MyRunner()
    ctx = RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))
    result = runner.run("hello", ctx)
    assert result.status == "completed"
