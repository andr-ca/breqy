"""Tests for A2A server structlog migration."""
from __future__ import annotations


def test_a2a_server_uses_structlog():
    """a2a.server module-level logger is structlog, not stdlib."""
    import logging as _logging
    from breqy.a2a import server
    assert hasattr(server, "logger")
    assert not isinstance(server.logger, _logging.Logger)
