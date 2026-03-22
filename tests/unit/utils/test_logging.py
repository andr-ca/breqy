"""Tests for structured logging setup."""
from __future__ import annotations


def test_setup_logging_does_not_raise():
    """setup_logging() with valid level runs without error."""
    from breqy.utils.logging import setup_logging
    setup_logging("INFO")  # must not raise


def test_setup_logging_debug_level():
    """setup_logging() accepts DEBUG level."""
    from breqy.utils.logging import setup_logging
    setup_logging("DEBUG")  # must not raise


def test_setup_logging_invalid_level_falls_back():
    """setup_logging() with unknown level falls back to INFO without raising."""
    from breqy.utils.logging import setup_logging
    setup_logging("BOGUS_LEVEL")  # must not raise
