"""Tests for A2A client structlog migration."""
from __future__ import annotations


def test_a2a_client_uses_structlog():
    """a2a.client module-level logger is structlog, not stdlib."""
    import logging as _logging
    from breqy.a2a import client
    assert hasattr(client, "logger")
    assert not isinstance(client.logger, _logging.Logger)
