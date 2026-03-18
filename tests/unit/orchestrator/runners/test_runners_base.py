import pytest
import subprocess
from pathlib import Path
from unittest.mock import MagicMock
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult


def test_agent_runner_is_abstract():
    with pytest.raises(TypeError):
        AgentRunner()


def test_start_is_abstract():
    """A subclass that only implements run() (not start()) cannot be instantiated."""
    class OnlyRunRunner(AgentRunner):
        def run(self, prompt: str, context: RunContext) -> RunResult:
            return RunResult(status="completed", output="", exit_code=0)
    with pytest.raises(TypeError):
        OnlyRunRunner()


def test_abc_run_default_calls_start_and_communicate():
    """The ABC's default run() calls start() then communicate()."""
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("hello", None)
    mock_proc.returncode = 0

    class MinimalRunner(AgentRunner):
        def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
            return mock_proc

    runner = MinimalRunner()
    ctx = RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))
    result = runner.run("hi", ctx)
    assert result.status == "completed"
    assert result.output == "hello"
    mock_proc.communicate.assert_called_once()


def test_runner_interface():
    class MyRunner(AgentRunner):
        def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
            return MagicMock(communicate=lambda: ("ok", None), returncode=0)

    runner = MyRunner()
    ctx = RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))
    result = runner.run("hello", ctx)
    assert result.status == "completed"
