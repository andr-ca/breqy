"""Tests for breqy.domain.ids — ULID-based ID generation."""
from __future__ import annotations


def test_generate_id_returns_26_char_string():
    from breqy.domain.ids import generate_id

    result = generate_id()
    assert isinstance(result, str), "generate_id() must return a str"
    assert len(result) == 26, f"ULID must be 26 chars, got {len(result)}"


def test_generate_id_is_unique():
    from breqy.domain.ids import generate_id

    ids = [generate_id() for _ in range(100)]
    assert len(set(ids)) == 100, "generate_id() must produce unique values"


def test_generate_prefixed_id_has_prefix():
    from breqy.domain.ids import generate_prefixed_id

    result = generate_prefixed_id("ses")
    assert result.startswith("ses_"), f"Expected 'ses_' prefix, got {result!r}"


def test_generate_prefixed_id_total_length():
    from breqy.domain.ids import generate_prefixed_id

    result = generate_prefixed_id("ses")
    # prefix "ses_" = 4 chars + 26 char ULID = 30
    assert len(result) == 30, f"Expected length 30, got {len(result)}"


def test_generate_prefixed_id_msg_prefix():
    from breqy.domain.ids import generate_prefixed_id

    result = generate_prefixed_id("msg")
    assert result.startswith("msg_"), f"Expected 'msg_' prefix, got {result!r}"
