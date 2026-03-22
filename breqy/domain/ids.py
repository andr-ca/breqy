"""ULID-based ID generation for all Breqy domain objects."""
from __future__ import annotations

from ulid import ULID


def generate_id() -> str:
    """Generate a new ULID string (26 characters)."""
    return str(ULID())


def generate_prefixed_id(prefix: str) -> str:
    """Generate a prefixed ULID string, e.g. 'ses_01ARZ3NDEKTSV4RRFFQ69G5FAV'."""
    return f"{prefix}_{generate_id()}"
