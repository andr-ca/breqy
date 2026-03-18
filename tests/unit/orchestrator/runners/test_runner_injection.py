# tests/unit/orchestrator/runners/test_runner_injection.py
from unittest.mock import patch, MagicMock
from pathlib import Path
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.schemas.run_result import RunContext


def _ctx():
    return RunContext(task_id="BRQ-1", role="doer", work_dir=Path("/tmp"))


def _mock_proc(output="done\n"):
    """Mock for all runners (calls proc.communicate())."""
    proc = MagicMock()
    proc.communicate.return_value = (output, None)
    proc.returncode = 0
    return proc


def test_claude_runner_injects_token():
    from system.orchestrator.runners.claude_runner import ClaudeRunner
    with patch("keyring.get_password", return_value="ant_TOKEN"), \
         patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _mock_proc()
        runner = ClaudeRunner(credential_store=CredentialStore())
        runner.run("hello", _ctx())
        env = mock_popen.call_args.kwargs["env"]
        assert env["ANTHROPIC_API_KEY"] == "ant_TOKEN"


def test_codex_runner_injects_token():
    from system.orchestrator.runners.codex_runner import CodexRunner
    with patch("keyring.get_password", return_value="oai_TOKEN"), \
         patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _mock_proc()
        runner = CodexRunner(credential_store=CredentialStore())
        runner.run("hello", _ctx())
        env = mock_popen.call_args.kwargs["env"]
        assert env["OPENAI_API_KEY"] == "oai_TOKEN"


def test_runner_without_store_still_works():
    """No CredentialStore — backward compatible, reads token from OS env."""
    from system.orchestrator.runners.claude_runner import ClaudeRunner
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = _mock_proc()
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
