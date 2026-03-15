from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from system.orchestrator.runners.claude_runner import ClaudeRunner
from system.orchestrator.schemas.run_result import RunContext


@pytest.fixture
def ctx():
    return RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))


def _proc(stdout="", returncode=0):
    m = MagicMock()
    # stdout must be a line-iterable (ClaudeRunner iterates `for line in proc.stdout`)
    m.stdout = iter(stdout.splitlines(keepends=True))
    m.stderr = ""
    m.returncode = returncode
    m.wait.return_value = returncode
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    return m


def test_claude_runner_success(ctx):
    with patch("subprocess.Popen", return_value=_proc(stdout='Result complete\n')):
        runner = ClaudeRunner()
        result = runner.run("do the thing", ctx)
    assert result.status == "completed"
    assert result.exit_code == 0


def test_claude_runner_rate_limit_detected(ctx):
    with patch("subprocess.Popen", return_value=_proc(
        stdout="rate_limit_error: too many requests", returncode=1
    )):
        runner = ClaudeRunner()
        result = runner.run("do the thing", ctx)
    assert result.status == "rate_limited"


def test_claude_runner_resumes_session(ctx):
    ctx_with_session = ctx.model_copy(update={"session_id": "sess-abc"})
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _proc(stdout="done\n")
        runner = ClaudeRunner()
        runner.run("do the thing", ctx_with_session)
        cmd = mock_popen.call_args[0][0]
        assert "--resume" in cmd
        assert "sess-abc" in cmd


def test_claude_runner_builds_correct_base_cmd(ctx):
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _proc(stdout="done\n")
        runner = ClaudeRunner()
        runner.run("prompt text", ctx)
        cmd = mock_popen.call_args[0][0]
        assert "claude" in cmd
        assert "--output-format" in cmd
        assert "stream-json" in cmd


def test_claude_runner_exit0_with_rate_limit_string_is_rate_limited(ctx):
    """Exit code 0 + rate-limit string → rate_limited, not completed."""
    with patch("subprocess.Popen", return_value=_proc(
        stdout="rate_limit_error: too many requests\n", returncode=0
    )):
        runner = ClaudeRunner()
        result = runner.run("do the thing", ctx)
    assert result.status == "rate_limited"
