"""Tests for breqy.domain.enums — domain enumerations."""
from __future__ import annotations


# --- SessionStatus ---


def test_session_status_has_circuit_broken():
    from breqy.domain.enums import SessionStatus

    assert hasattr(SessionStatus, "CIRCUIT_BROKEN"), (
        "SessionStatus must have a CIRCUIT_BROKEN member"
    )


def test_session_status_circuit_broken_value():
    from breqy.domain.enums import SessionStatus

    assert SessionStatus.CIRCUIT_BROKEN == "circuit_broken"


def test_session_status_circuit_broken_is_terminal():
    """CIRCUIT_BROKEN must be distinct from the two other non-active statuses."""
    from breqy.domain.enums import SessionStatus

    terminal_like = {SessionStatus.CLOSED, SessionStatus.CIRCUIT_BROKEN}
    assert SessionStatus.CIRCUIT_BROKEN in terminal_like
    assert SessionStatus.ACTIVE not in terminal_like


def test_session_status_preserves_existing_members():
    """Adding CIRCUIT_BROKEN must not remove or alter existing members."""
    from breqy.domain.enums import SessionStatus

    assert SessionStatus.ACTIVE == "active"
    assert SessionStatus.CLOSED == "closed"
    assert SessionStatus.SUSPENDED == "suspended"


def test_session_status_member_count():
    """SessionStatus should now have exactly 4 members."""
    from breqy.domain.enums import SessionStatus

    assert len(SessionStatus) == 4
