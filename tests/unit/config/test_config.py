"""Tests for config models."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from breqy.config.models import AgentConfig, EngineConfig, MCPServerConfig


def test_engine_config_defaults(monkeypatch):
    """EngineConfig has sensible defaults when no env vars are set."""
    monkeypatch.delenv("BREQY_ENGINE_SOCKET", raising=False)
    monkeypatch.delenv("BREQY_DATA_DIR", raising=False)
    monkeypatch.delenv("BREQY_DB_PATH", raising=False)
    monkeypatch.delenv("BREQY_LOG_LEVEL", raising=False)
    cfg = EngineConfig()
    assert cfg.socket_path == "/tmp/breqy-engine.sock"
    from pathlib import Path
    assert cfg.data_dir == str(Path.home() / ".breqy" / "data")
    assert cfg.db_path == str(Path.home() / ".breqy" / "data" / "breqy.db")
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


# ---------------------------------------------------------------------------
# Path expansion (model_validator)
# ---------------------------------------------------------------------------


def test_engine_config_expands_tilde_in_socket_path(monkeypatch):
    """EngineConfig resolves ~ in socket_path to home directory."""
    monkeypatch.delenv("BREQY_ENGINE_SOCKET", raising=False)
    monkeypatch.delenv("BREQY_DATA_DIR", raising=False)
    monkeypatch.delenv("BREQY_DB_PATH", raising=False)
    cfg = EngineConfig(
        socket_path="~/breqy/engine.sock",
        data_dir="/tmp/data",
        db_path="/tmp/data/breqy.db",
    )
    assert "~" not in cfg.socket_path
    assert cfg.socket_path == str(Path(Path.home() / "breqy" / "engine.sock").resolve())


def test_engine_config_expands_tilde_in_data_dir(monkeypatch):
    """EngineConfig resolves ~ in data_dir."""
    monkeypatch.delenv("BREQY_ENGINE_SOCKET", raising=False)
    monkeypatch.delenv("BREQY_DATA_DIR", raising=False)
    monkeypatch.delenv("BREQY_DB_PATH", raising=False)
    cfg = EngineConfig(
        socket_path="/tmp/engine.sock",
        data_dir="~/.local/share/breqy",
        db_path="/tmp/data/breqy.db",
    )
    assert "~" not in cfg.data_dir
    assert cfg.data_dir == str(Path(Path.home() / ".local" / "share" / "breqy").resolve())


def test_engine_config_expands_tilde_in_db_path(monkeypatch):
    """EngineConfig resolves ~ in db_path."""
    monkeypatch.delenv("BREQY_ENGINE_SOCKET", raising=False)
    monkeypatch.delenv("BREQY_DATA_DIR", raising=False)
    monkeypatch.delenv("BREQY_DB_PATH", raising=False)
    cfg = EngineConfig(
        socket_path="/tmp/engine.sock",
        data_dir="/tmp/data",
        db_path="~/breqy/breqy.db",
    )
    assert "~" not in cfg.db_path
    assert cfg.db_path == str(Path(Path.home() / "breqy" / "breqy.db").resolve())


def test_engine_config_expands_env_vars_in_paths(monkeypatch):
    """EngineConfig resolves $VAR references in path fields."""
    monkeypatch.setenv("BREQY_CUSTOM_BASE", "/opt/breqy")
    monkeypatch.delenv("BREQY_ENGINE_SOCKET", raising=False)
    monkeypatch.delenv("BREQY_DATA_DIR", raising=False)
    monkeypatch.delenv("BREQY_DB_PATH", raising=False)
    cfg = EngineConfig(
        socket_path="$BREQY_CUSTOM_BASE/engine.sock",
        data_dir="$BREQY_CUSTOM_BASE/data",
        db_path="$BREQY_CUSTOM_BASE/data/breqy.db",
    )
    assert cfg.socket_path == str(Path("/opt/breqy/engine.sock").resolve())
    assert cfg.data_dir == str(Path("/opt/breqy/data").resolve())
    assert cfg.db_path == str(Path("/opt/breqy/data/breqy.db").resolve())


def test_engine_config_paths_are_always_absolute(monkeypatch):
    """model_validator ensures all paths are resolved to absolute form."""
    monkeypatch.delenv("BREQY_ENGINE_SOCKET", raising=False)
    monkeypatch.delenv("BREQY_DATA_DIR", raising=False)
    monkeypatch.delenv("BREQY_DB_PATH", raising=False)
    cfg = EngineConfig(
        socket_path="relative/engine.sock",
        data_dir="relative/data",
        db_path="relative/data/breqy.db",
    )
    assert Path(cfg.socket_path).is_absolute()
    assert Path(cfg.data_dir).is_absolute()
    assert Path(cfg.db_path).is_absolute()


def test_agent_config_required_fields():
    """AgentConfig requires id, name, provider, and model."""
    cfg = AgentConfig(
        id="breqy",
        name="Breqy Agent",
        provider="copilot",
        model="gpt-4o",
    )
    assert cfg.id == "breqy"
    assert cfg.name == "Breqy Agent"
    assert cfg.provider == "copilot"
    assert cfg.model == "gpt-4o"
    assert cfg.autonomy_level == "supervised"
    assert isinstance(cfg.tool_permissions, list)


def test_agent_config_requires_provider() -> None:
    """AgentConfig rejects manifests without a provider."""
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"id": "breqy", "name": "Breqy Agent", "model": "gpt-4o"})


@pytest.mark.parametrize(
    "provider",
    ["copilot", "codex", "claude", "gemini", "qwen"],
)
def test_agent_config_accepts_supported_provider_values(provider: str) -> None:
    """AgentConfig accepts every supported provider identifier."""
    cfg = AgentConfig(
        id="breqy",
        name="Breqy Agent",
        provider=provider,
        model="gpt-4o",
    )

    assert cfg.provider == provider


def test_agent_config_rejects_unsupported_provider_value() -> None:
    """AgentConfig rejects unsupported provider identifiers."""
    with pytest.raises(ValidationError):
        AgentConfig(
            id="breqy",
            name="Breqy Agent",
            provider="openai",
            model="gpt-4o",
        )


def test_agent_config_requires_model() -> None:
    """AgentConfig rejects manifests without a model."""
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"id": "breqy", "name": "Breqy Agent", "provider": "copilot"})


def test_agent_config_rejects_blank_model() -> None:
    with pytest.raises(ValidationError, match="model must not be empty"):
        AgentConfig(id="breqy", name="Breqy Agent", provider="copilot", model="   ")


def test_agent_config_accepts_provider_settings() -> None:
    """AgentConfig keeps optional provider settings."""
    cfg = AgentConfig(
        id="breqy",
        name="Breqy Agent",
        provider="copilot",
        model="gpt-4o",
        provider_settings={"temperature": "0", "mode": "balanced"},
    )

    assert cfg.provider_settings == {"temperature": "0", "mode": "balanced"}


def test_agent_config_preserves_skill_permission_wildcard() -> None:
    """AgentConfig allows wildcard skill permissions as a single-item list."""
    cfg = AgentConfig(
        id="breqy",
        name="Breqy Agent",
        provider="copilot",
        model="gpt-4o",
        skill_permissions=["*"],
    )

    assert cfg.skill_permissions == ["*"]


def test_agent_config_rejects_blank_skill_permissions() -> None:
    with pytest.raises(ValidationError, match="skill permissions must not be empty"):
        AgentConfig(
            id="breqy",
            name="Breqy Agent",
            provider="copilot",
            model="gpt-4o",
            skill_permissions=["plan", "  "],
        )


def test_agent_config_rejects_mixed_skill_wildcard() -> None:
    with pytest.raises(ValidationError, match="wildcard"):
        AgentConfig(
            id="breqy",
            name="Breqy Agent",
            provider="copilot",
            model="gpt-4o",
            skill_permissions=["*", "plan"],
        )


@pytest.mark.parametrize("invalid_id", ["", "Upper", "bad_id", "white space"])
def test_mcp_server_config_rejects_invalid_id(invalid_id: str) -> None:
    with pytest.raises(ValidationError, match="MCP server id"):
        MCPServerConfig(id=invalid_id, transport="process", command="server")


def test_mcp_server_config_normalizes_valid_id() -> None:
    cfg = MCPServerConfig(id="server-1", transport="process", command="server")

    assert cfg.id == "server-1"


def test_agent_config_full():
    """AgentConfig accepts all optional fields."""
    cfg = AgentConfig(
        id="test-agent",
        name="Test Agent",
        provider="claude",
        model="sonnet",
        display_name="Test",
        port=9000,
        autonomy_level="autonomous",
        tool_permissions=["shell", "fs"],
        provider_settings={"workspace": "default"},
        skill_permissions=["plan", "review"],
    )
    assert cfg.port == 9000
    assert cfg.tool_permissions == ["shell", "fs"]
    assert cfg.provider_settings == {"workspace": "default"}
    assert cfg.skill_permissions == ["plan", "review"]


from breqy.config.loader import load_agent_config, load_engine_config


def test_load_engine_config_no_file():
    """load_engine_config() with no path returns defaults."""
    cfg = load_engine_config()
    assert isinstance(cfg, EngineConfig)


def test_load_engine_config_from_yaml(tmp_path):
    """load_engine_config() with valid YAML overrides defaults."""
    config_file = tmp_path / "engine.yaml"
    config_file.write_text(yaml.dump({"socket_path": "/tmp/my.sock", "log_level": "DEBUG"}))
    cfg = load_engine_config(str(config_file))
    assert cfg.socket_path == "/tmp/my.sock"
    assert cfg.log_level == "DEBUG"


def test_load_agent_config_valid(tmp_path):
    """load_agent_config() reads agent.yaml and persona.md from directory."""
    (tmp_path / "agent.yaml").write_text(
        yaml.dump(
            {
                "id": "my-agent",
                "name": "My Agent",
                "provider": "copilot",
                "model": "gpt-4o",
                "autonomy_level": "supervised",
            }
        )
    )
    persona_file = tmp_path / "persona.md"
    persona_file.write_text("You are calm and sharp.\n")

    cfg = load_agent_config(str(tmp_path))

    assert cfg.id == "my-agent"
    assert cfg.name == "My Agent"
    assert cfg.persona_path == str(persona_file.resolve())
    assert cfg.persona_content == "You are calm and sharp.\n"


def test_load_agent_config_missing_file(tmp_path):
    """load_agent_config() raises FileNotFoundError if agent.yaml absent."""
    with pytest.raises(FileNotFoundError):
        load_agent_config(str(tmp_path))


def test_load_agent_config_missing_persona_file(tmp_path: Path) -> None:
    """load_agent_config() raises FileNotFoundError if persona.md is absent."""
    (tmp_path / "agent.yaml").write_text(
        yaml.dump(
            {
                "id": "my-agent",
                "name": "My Agent",
                "provider": "copilot",
                "model": "gpt-4o",
            }
        )
    )

    with pytest.raises(FileNotFoundError):
        load_agent_config(str(tmp_path))


def test_load_agent_config_rejects_absolute_persona_path(tmp_path: Path) -> None:
    """load_agent_config() rejects persona files outside the agent directory."""
    outside_persona = tmp_path / "outside-persona.md"
    outside_persona.write_text("outside\n")
    (tmp_path / "agent.yaml").write_text(
        yaml.dump(
            {
                "id": "my-agent",
                "name": "My Agent",
                "provider": "copilot",
                "model": "gpt-4o",
                "persona_file": str(outside_persona.resolve()),
            }
        )
    )

    with pytest.raises(ValueError, match="persona_file"):
        load_agent_config(str(tmp_path))


def test_load_agent_config_rejects_parent_traversal_persona_path(tmp_path: Path) -> None:
    """load_agent_config() rejects parent traversal in persona_file."""
    (tmp_path / "agent.yaml").write_text(
        yaml.dump(
            {
                "id": "my-agent",
                "name": "My Agent",
                "provider": "copilot",
                "model": "gpt-4o",
                "persona_file": "../persona.md",
            }
        )
    )

    with pytest.raises(ValueError, match="persona_file"):
        load_agent_config(str(tmp_path))


def test_load_agent_config_rejects_persona_directory_target(tmp_path: Path) -> None:
    """load_agent_config() rejects persona_file values that resolve to directories."""
    persona_dir = tmp_path / "persona-dir"
    persona_dir.mkdir()
    (tmp_path / "agent.yaml").write_text(
        yaml.dump(
            {
                "id": "my-agent",
                "name": "My Agent",
                "provider": "copilot",
                "model": "gpt-4o",
                "persona_file": "persona-dir",
            }
        )
    )

    with pytest.raises(ValueError, match="persona_file"):
        load_agent_config(str(tmp_path))


def test_load_checked_in_default_agent_definition() -> None:
    """The checked-in default agent definition resolves its persona from disk."""
    repo_root = Path(__file__).resolve().parents[3]

    cfg = load_agent_config(str(repo_root / "agents" / "breqy"))

    assert cfg.id == "breqy"
    assert cfg.provider == "copilot"
    assert cfg.persona_path == str((repo_root / "agents" / "breqy" / "persona.md").resolve())
    assert cfg.persona_content is not None
    assert "You are Breqy." in cfg.persona_content
    assert "slightly disruptive" in cfg.persona_content


@pytest.mark.parametrize("yaml_content", ["- item\n", "42\n", "true\n"])
def test_load_agent_config_rejects_non_mapping_yaml(tmp_path: Path, yaml_content: str) -> None:
    """load_agent_config() rejects agent manifests that are not YAML mappings."""
    (tmp_path / "agent.yaml").write_text(yaml_content)

    with pytest.raises(ValueError, match="agent.yaml"):
        load_agent_config(str(tmp_path))


def test_load_agent_config_invalid_yaml(tmp_path):
    """load_agent_config() raises ValidationError for missing required fields."""
    (tmp_path / "agent.yaml").write_text(yaml.dump({"display_name": "Missing id and name"}))
    with pytest.raises(ValidationError):
        load_agent_config(str(tmp_path))


def test_load_agent_config_empty_yaml_uses_empty_mapping_then_fails_validation(tmp_path: Path) -> None:
    (tmp_path / "agent.yaml").write_text("")

    with pytest.raises(ValidationError):
        load_agent_config(str(tmp_path))


# ============================================================================ #
# Observability: Task 10 — log_dir property on EngineConfig
# ============================================================================ #


def test_engine_config_log_dir(tmp_path: Path) -> None:
    """EngineConfig.log_dir should be derived from data_dir."""
    config = EngineConfig(data_dir=str(tmp_path / "data"))
    assert config.log_dir == str(tmp_path / "data" / "logs")
