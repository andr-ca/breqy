import pytest
from unittest.mock import patch, MagicMock
from system.orchestrator.branch_manager import BranchManager, BranchError


@pytest.fixture
def bm(tmp_path):
    return BranchManager(repo_root=tmp_path)


def _run_ok(cmd=None, **_):
    m = MagicMock()
    m.returncode = 0
    m.stdout = ""
    m.stderr = ""
    return m


def test_make_slug():
    assert BranchManager.make_slug("Session resume flow and retry") == "session-resume-flow-and-retry"
    assert BranchManager.make_slug("Fix: reconnect!") == "fix-reconnect"
    assert len(BranchManager.make_slug("x" * 100)) == 40


def test_branch_name_feature(bm):
    slug = BranchManager.make_slug("session resume flow and retry")
    name = bm._make_branch_name("BRQ-144", "feature", slug)
    assert name.startswith("feat/BRQ-144-")
    assert " " not in name


def test_branch_name_bug(bm):
    assert bm._make_branch_name("BRQ-201", "bug", "fix-reconnect").startswith("fix/")


def test_branch_name_refactor(bm):
    assert bm._make_branch_name("BRQ-233", "refactor", "cleanup").startswith("refactor/")


def test_branch_name_hotfix(bm):
    assert bm._make_branch_name("BRQ-299", "hotfix", "critical-auth").startswith("hotfix/")


def test_create_branch_calls_git_checkout(bm):
    with patch("subprocess.run", side_effect=_run_ok) as mock_run:
        name = bm.create_branch("BRQ-1", "feature", "session-resume")
        calls = " ".join(str(c) for c in mock_run.call_args_list)
        assert "checkout" in calls
        assert "-b" in calls
    assert name == "feat/BRQ-1-session-resume"


def test_current_branch_returns_name(bm):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="feat/BRQ-1-test\n", stderr="")
        assert bm.current_branch() == "feat/BRQ-1-test"


def test_is_stale_false_for_recent(bm):
    import time
    recent_ts = str(int(time.time()) - 60)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=recent_ts, stderr="")
        assert not bm.is_stale("feat/BRQ-1-test", max_age_days=3)


def test_is_stale_true_for_old(bm):
    import time
    old_ts = str(int(time.time()) - 7 * 86400)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=old_ts, stderr="")
        assert bm.is_stale("feat/BRQ-1-test", max_age_days=3)


def test_rebase_calls_git_rebase(bm):
    with patch("subprocess.run", side_effect=_run_ok) as mock_run:
        bm.rebase("feat/BRQ-1-test", "dev")
        calls = " ".join(str(c) for c in mock_run.call_args_list)
        assert "rebase" in calls


def test_merge_target_feature(bm):
    assert bm.merge_target("feature") == "dev"


def test_merge_target_hotfix(bm):
    assert bm.merge_target("hotfix") == "main"


def test_merge_target_bug_and_refactor(bm):
    assert bm.merge_target("bug") == "dev"
    assert bm.merge_target("refactor") == "dev"


def test_branch_exists_true(bm):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert bm.branch_exists("feat/BRQ-1-test")


def test_branch_exists_false(bm):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        assert not bm.branch_exists("feat/BRQ-1-test")


def test_push_calls_git(bm):
    with patch("subprocess.run", side_effect=_run_ok) as mock_run:
        bm.push("feat/BRQ-1-test")
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("push" in c for c in calls)
