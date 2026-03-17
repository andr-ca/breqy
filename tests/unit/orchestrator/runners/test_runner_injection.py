# tests/unit/orchestrator/runners/test_runner_injection.py
from unittest.mock import patch, MagicMock
from pathlib import Path
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.schemas.run_result import RunContext


def _ctx():
    return RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))


def _mock_proc_iterating(output="done\n"):
    """Mock for ClaudeRunner (iterates proc.stdout line by line)."""
    proc = MagicMock()
    proc.stdout = iter([output])
    proc.returncode = 0
    proc.wait.return_value = 0
    return proc


def _mock_proc_read(output="done"):
    """Mock for other runners (calls proc.stdout.read())."""
    proc = MagicMock()
    proc.stdout.read.return_value = output
    proc.returncode = 0
    proc.wait.return_value = 0
    return proc


def test_claude_runner_injects_token():
    from system.orchestrator.runners.claude_runner import ClaudeRunner
    with patch("keyring.get_password", return_value="ant_TOKEN"), \
         patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _mock_proc_iterating()
        runner = ClaudeRunner(credential_store=CredentialStore())
        runner.run("hello", _ctx())
        env = mock_popen.call_args.kwargs["env"]
        assert env["ANTHROPIC_API_KEY"] == "ant_TOKEN"


def test_codex_runner_injects_token():
    from system.orchestrator.runners.codex_runner import CodexRunner
    with patch("keyring.get_password", return_value="oai_TOKEN"), \
         patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _mock_proc_read()
        runner = CodexRunner(credential_store=CredentialStore())
        runner.run("hello", _ctx())
        env = mock_popen.call_args.kwargs["env"]
        assert env["OPENAI_API_KEY"] == "oai_TOKEN"


def test_runner_without_store_still_works():
    """No CredentialStore — backward compatible, reads token from OS env."""
    from system.orchestrator.runners.claude_runner import ClaudeRunner
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _mock_proc_iterating()
        ClaudeRunner().run("hello", _ctx())  # must not raise


def test_router_passes_store_to_runner():
    from system.orchestrator.router import Router
    from system.orchestrator.config import OrchestratorConfig, GitHubConfig
    with patch("keyring.get_password", return_value=None):
        store = CredentialStore()
        cfg = OrchestratorConfig(
            github=GitHubConfig(repo="o/r"),
            agent_defaults={"doer": "claude"},
        )
        router = Router(config=cfg, credential_store=store)
        runner, _ = router.resolve("feature", "backend", "doer")
        assert runner._store is store
