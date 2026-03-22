"""Tests for config models."""
from __future__ import annotations

import os

import pytest

from breqy.config.models import AgentConfig, EngineConfig


def test_engine_config_defaults():
    """EngineConfig has sensible defaults from env or hardcoded fallback."""
    cfg = EngineConfig()
    assert cfg.socket_path  # non-empty
    assert cfg.data_dir  # non-empty
    assert cfg.db_path  # non-empty
    assert cfg.log_level == "INFO"
    assert cfg.default_agent_id == "breqy"


def test_engine_config_from_env(monkeypatch):
    """EngineConfig reads from BREQY_* env vars."""
    monkeypatch.setenv("BREQY_ENGINE_SOCKET", "/tmp/test.sock")
    monkeypatch.setenv("BREQY_DATA_DIR", "/tmp/data")
    monkeypatch.setenv("BREQY_DB_PATH", "/tmp/data/breqy.db")
    monkeypatch.setenv("BREQY_LOG_LEVEL", "DEBUG")
    cfg = EngineConfig()
    assert cfg.socket_path == "/tmp/test.sock"
    assert cfg.data_dir == "/tmp/data"
    assert cfg.db_path == "/tmp/data/breqy.db"
    assert cfg.log_level == "DEBUG"


def test_agent_config_required_fields():
    """AgentConfig requires id and name; others have defaults."""
    cfg = AgentConfig(id="breqy", name="Breqy Agent")
    assert cfg.id == "breqy"
    assert cfg.name == "Breqy Agent"
    assert cfg.autonomy_level == "supervised"
    assert isinstance(cfg.tool_permissions, list)


def test_agent_config_full():
    """AgentConfig accepts all optional fields."""
    cfg = AgentConfig(
        id="test-agent",
        name="Test Agent",
        display_name="Test",
        port=9000,
        autonomy_level="autonomous",
        tool_permissions=["shell", "fs"],
    )
    assert cfg.port == 9000
    assert cfg.tool_permissions == ["shell", "fs"]
