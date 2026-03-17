import pytest
from unittest.mock import patch, MagicMock
from system.orchestrator.session_manager import SessionManager, is_rate_limit_output


def test_is_rate_limit_output_positive():
    assert is_rate_limit_output("Error: Claude AI rate limit exceeded")
    assert is_rate_limit_output("claude: rate_limit_error: too many requests")
    assert is_rate_limit_output("Overloaded")


def test_is_rate_limit_output_negative():
    assert not is_rate_limit_output("Implementation complete")
    assert not is_rate_limit_output("")
    assert not is_rate_limit_output("Error: file not found")


def test_session_manager_stores_session_id():
    sm = SessionManager()
    sm.save_session("BRQ-1", "doer", "sess-abc-123")
    assert sm.get_session("BRQ-1", "doer") == "sess-abc-123"


def test_session_manager_returns_none_for_unknown():
    sm = SessionManager()
    assert sm.get_session("BRQ-999", "doer") is None


def test_session_manager_overwrite():
    sm = SessionManager()
    sm.save_session("BRQ-1", "doer", "old-id")
    sm.save_session("BRQ-1", "doer", "new-id")
    assert sm.get_session("BRQ-1", "doer") == "new-id"


def test_ccusage_available_when_zero_blocks():
    sm = SessionManager()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='{"blocks": 0}', stderr="")
        assert sm.is_window_available()


def test_ccusage_blocked_when_blocks_nonzero():
    sm = SessionManager()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='{"blocks": 2}', stderr="")
        assert not sm.is_window_available()
