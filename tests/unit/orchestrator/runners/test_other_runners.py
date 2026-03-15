from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from system.orchestrator.runners.codex_runner import CodexRunner
from system.orchestrator.runners.copilot_runner import CopilotRunner
from system.orchestrator.runners.gemini_runner import GeminiRunner
from system.orchestrator.runners.qwen_runner import QwenRunner
from system.orchestrator.schemas.run_result import RunContext


@pytest.fixture
def ctx():
    return RunContext(task_id="BRQ-1", role="checker", work_dir=Path("/tmp"))


def _proc(stdout="done\n", returncode=0):
    m = MagicMock()
    stdout_mock = MagicMock()
    stdout_mock.read.return_value = stdout
    m.stdout = stdout_mock
    m.returncode = returncode
    m.wait.return_value = returncode
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    return m


@pytest.mark.parametrize("RunnerCls,expected_cmd_token", [
    (CodexRunner, "codex"),
    (GeminiRunner, "gemini"),
    (CopilotRunner, "gh"),
    (QwenRunner, "qwen"),
])
def test_runner_invokes_correct_cli(RunnerCls, expected_cmd_token, ctx):
    with patch("subprocess.Popen", return_value=_proc()) as mock_popen:
        runner = RunnerCls()
        result = runner.run("check this code", ctx)
    cmd = mock_popen.call_args[0][0]
    assert expected_cmd_token in cmd
    assert result.status == "completed"


@pytest.mark.parametrize("RunnerCls", [CodexRunner, GeminiRunner, CopilotRunner, QwenRunner])
def test_runner_returns_failed_on_nonzero_exit(RunnerCls, ctx):
    with patch("subprocess.Popen", return_value=_proc(stdout="error output", returncode=1)):
        runner = RunnerCls()
        result = runner.run("check this code", ctx)
    assert result.status == "failed"
    assert result.exit_code == 1
