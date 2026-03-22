"""
Tests for slice1-task-01: Project Setup & Tooling.

Each test maps to an acceptance criterion from the task spec.
"""
from __future__ import annotations

import os
from pathlib import Path

import aiosqlite
import pytest


# --------------------------------------------------------------------------- #
# Helper: project root is two levels up from tests/unit/
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).parent.parent.parent


# --------------------------------------------------------------------------- #
# AC: breqy/__init__.py exports __version__ = '0.1.0'
# AC: python -c 'import breqy; print(breqy.__version__)' prints 0.1.0
# --------------------------------------------------------------------------- #
def test_breqy_version_is_importable():
    import breqy

    assert hasattr(breqy, "__version__"), "breqy must export __version__"
    assert breqy.__version__ == "0.1.0", f"expected '0.1.0', got {breqy.__version__!r}"


# --------------------------------------------------------------------------- #
# AC: breqy/py.typed exists (PEP 561 marker)
# --------------------------------------------------------------------------- #
def test_py_typed_marker_exists():
    marker = PROJECT_ROOT / "breqy" / "py.typed"
    assert marker.exists(), f"PEP 561 marker missing: {marker}"
    assert marker.is_file(), "py.typed must be a regular file"


# --------------------------------------------------------------------------- #
# AC: pyproject.toml has all required deps + dev extras
# We check pyproject.toml content rather than installed packages because the
# criterion is about the declared configuration, and the install environment
# varies (uv-managed venv vs system Python running pytest).
# --------------------------------------------------------------------------- #
def test_pyproject_required_runtime_deps():
    pyproject = PROJECT_ROOT / "pyproject.toml"
    assert pyproject.exists(), "pyproject.toml is missing"
    content = pyproject.read_text()

    required = [
        "pydantic>=2",
        "aiosqlite",
        "textual",
        "structlog",
        "python-ulid",
        "keyring",
        "pyyaml",
    ]
    for spec in required:
        assert spec in content, f"pyproject.toml missing required dependency: {spec}"


def test_pyproject_dev_deps_declared():
    pyproject = PROJECT_ROOT / "pyproject.toml"
    content = pyproject.read_text()

    dev_deps = ["pytest", "pytest-asyncio", "pytest-cov", "ruff", "mypy"]
    for pkg in dev_deps:
        assert pkg in content, f"pyproject.toml missing dev dependency: {pkg}"


# --------------------------------------------------------------------------- #
# AC: .env.sample documents the four required env vars
# --------------------------------------------------------------------------- #
def test_env_sample_documents_required_vars():
    env_sample = PROJECT_ROOT / ".env.sample"
    assert env_sample.exists(), ".env.sample is missing"

    content = env_sample.read_text()
    required_vars = [
        "BREQY_ENGINE_SOCKET",
        "BREQY_DATA_DIR",
        "BREQY_LOG_LEVEL",
        "BREQY_DB_PATH",
    ]
    for var in required_vars:
        assert var in content, f".env.sample missing required var: {var}"


# --------------------------------------------------------------------------- #
# AC: .env exists and is gitignored
# --------------------------------------------------------------------------- #
def test_env_file_exists():
    env = PROJECT_ROOT / ".env"
    assert env.exists(), ".env file must exist"


def test_env_is_gitignored():
    gitignore = PROJECT_ROOT / ".gitignore"
    assert gitignore.exists(), ".gitignore missing"
    content = gitignore.read_text()
    assert ".env" in content, ".env must be listed in .gitignore"


# --------------------------------------------------------------------------- #
# AC: tests/conftest.py provides tmp_dir, db_path, db_connection, socket_path
# These tests USE the fixtures — they fail if conftest.py doesn't define them.
# --------------------------------------------------------------------------- #
def test_tmp_dir_fixture_provides_existing_directory(tmp_dir: Path):
    assert tmp_dir.exists(), "tmp_dir must point to an existing directory"
    assert tmp_dir.is_dir(), "tmp_dir must be a directory"


def test_db_path_fixture_is_under_tmp_dir(db_path: Path, tmp_dir: Path):
    assert str(db_path).startswith(str(tmp_dir)), (
        "db_path must be inside tmp_dir"
    )
    assert db_path.suffix == ".db", "db_path must have .db extension"


@pytest.mark.asyncio
async def test_db_connection_fixture_is_usable(db_connection: aiosqlite.Connection):
    cursor = await db_connection.execute("SELECT 1")
    row = await cursor.fetchone()
    assert row[0] == 1, "db_connection must return a working aiosqlite connection"


def test_socket_path_fixture_is_under_tmp_dir(socket_path: Path, tmp_dir: Path):
    assert str(socket_path).startswith(str(tmp_dir)), (
        "socket_path must be inside tmp_dir"
    )
