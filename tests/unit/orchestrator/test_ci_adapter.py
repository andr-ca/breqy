import json
import pytest
from unittest.mock import patch, MagicMock, call
from system.orchestrator.ci_adapter import CIAdapter, CiRun


def _run_ok(stdout=""):
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    m.stderr = ""
    return m


@pytest.fixture
def ci():
    return CIAdapter(repo="owner/repo", poll_interval_seconds=0)


def test_get_latest_run_success(ci):
    payload = json.dumps(
        [
            {
                "databaseId": 1,
                "status": "completed",
                "conclusion": "success",
                "headBranch": "feat/BRQ-1",
            }
        ]
    )
    with patch("subprocess.run", return_value=_run_ok(payload)):
        run = ci.get_latest_run("feat/BRQ-1")
        assert run.conclusion == "success"
        assert run.status == "completed"


def test_get_latest_run_no_runs_returns_none(ci):
    with patch("subprocess.run", return_value=_run_ok("[]")):
        assert ci.get_latest_run("feat/BRQ-1") is None


def test_wait_for_green_immediate(ci):
    payload = json.dumps(
        [
            {
                "databaseId": 1,
                "status": "completed",
                "conclusion": "success",
                "headBranch": "feat/BRQ-1",
            }
        ]
    )
    with patch("subprocess.run", return_value=_run_ok(payload)):
        assert ci.wait_for_green("feat/BRQ-1", timeout_minutes=1)


def test_wait_for_green_failure_returns_false(ci):
    payload = json.dumps(
        [
            {
                "databaseId": 1,
                "status": "completed",
                "conclusion": "failure",
                "headBranch": "feat/BRQ-1",
            }
        ]
    )
    with patch("subprocess.run", return_value=_run_ok(payload)):
        assert not ci.wait_for_green("feat/BRQ-1", timeout_minutes=1)


def test_wait_for_green_timeout_returns_false(ci):
    # in_progress run — never completes
    payload = json.dumps(
        [
            {
                "databaseId": 1,
                "status": "in_progress",
                "conclusion": None,
                "headBranch": "feat/BRQ-1",
            }
        ]
    )
    with patch("subprocess.run", return_value=_run_ok(payload)):
        # timeout_minutes=0 expires immediately
        assert not ci.wait_for_green("feat/BRQ-1", timeout_minutes=0)
