import json
import pytest
from unittest.mock import patch, MagicMock
from system.orchestrator.github_adapter import GitHubAdapter, PrStatus


def _run_ok(stdout="", returncode=0):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = ""
    return m


@pytest.fixture
def gh():
    return GitHubAdapter(repo="owner/repo")


def test_set_task_state_adds_new_label(gh):
    with patch("subprocess.run", return_value=_run_ok()) as mock_run:
        gh.set_task_state(42, "DOER_IN_PROGRESS")
        calls = " ".join(str(c) for c in mock_run.call_args_list)
        assert "state:DOER_IN_PROGRESS" in calls
        assert "--add-label" in calls


def test_set_task_state_removes_old_label(gh):
    with patch("subprocess.run", return_value=_run_ok()) as mock_run:
        gh.set_task_state(42, "DOER_IN_PROGRESS", old_state="READY_FOR_DOER")
        calls = " ".join(str(c) for c in mock_run.call_args_list)
        assert "state:READY_FOR_DOER" in calls   # old label removed
        assert "--remove-label" in calls
        assert "state:DOER_IN_PROGRESS" in calls  # new label added


def test_get_task_state_returns_state(gh):
    payload = json.dumps({"labels": [{"name": "orchestrator:managed"}, {"name": "state:READY_FOR_DOER"}]})
    with patch("subprocess.run", return_value=_run_ok(stdout=payload)):
        state = gh.get_task_state(42)
    assert state == "READY_FOR_DOER"


def test_get_task_state_returns_none_when_no_state_label(gh):
    payload = json.dumps({"labels": [{"name": "orchestrator:managed"}]})
    with patch("subprocess.run", return_value=_run_ok(stdout=payload)):
        assert gh.get_task_state(42) is None


def test_create_pr_returns_url(gh):
    pr_url = "https://github.com/owner/repo/pull/5"
    with patch("subprocess.run", return_value=_run_ok(stdout=pr_url)):
        url = gh.create_pr("feat/BRQ-1-test", "My PR", "Body text")
        assert url == pr_url.strip()


def test_pr_is_merged_true(gh):
    with patch("subprocess.run", return_value=_run_ok(stdout='{"state":"MERGED"}')):
        assert gh.pr_is_merged("https://github.com/owner/repo/pull/5")


def test_pr_is_merged_false(gh):
    with patch("subprocess.run", return_value=_run_ok(stdout='{"state":"OPEN"}')):
        assert not gh.pr_is_merged("https://github.com/owner/repo/pull/5")


def test_get_pr_status(gh):
    payload = json.dumps({"state": "OPEN", "mergeable": "MERGEABLE", "url": "http://x"})
    with patch("subprocess.run", return_value=_run_ok(stdout=payload)):
        status = gh.get_pr_status("http://x")
        assert status.state == "OPEN"
