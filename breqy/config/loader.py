"""Load configuration from YAML files and environment."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import yaml

from breqy.config.models import AgentConfig, EngineConfig


def _resolve_persona_path(agent_path: Path, persona_file: str) -> Path:
    persona_relative_path = Path(persona_file)
    if persona_relative_path.is_absolute():
        raise ValueError("persona_file must stay within the agent directory")

    persona_path = (agent_path / persona_relative_path).resolve()
    try:
        persona_path.relative_to(agent_path.resolve())
    except ValueError as exc:
        raise ValueError("persona_file must stay within the agent directory") from exc

    if persona_path.is_dir():
        raise ValueError("persona_file must reference a file, not a directory")

    return persona_path


def load_engine_config(config_path: str | None = None) -> EngineConfig:
    """Load engine config from env vars, optionally supplemented by YAML."""
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return EngineConfig(**data)
    return EngineConfig()


def load_agent_config(agent_dir: str) -> AgentConfig:
    """Load agent config and resolved persona from an agent directory."""
    agent_path = Path(agent_dir)
    config_path = agent_path / "agent.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Agent config not found: {config_path}")
    with open(config_path) as f:
        data = yaml.safe_load(f)
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        raise TypeError(f"Agent config in {config_path} must be a YAML mapping/object")
    config = AgentConfig(**data)
    persona_path = _resolve_persona_path(agent_path, config.persona_file)
    if not persona_path.exists():
        raise FileNotFoundError(f"Agent persona not found: {persona_path}")
    with open(persona_path) as f:
        persona_content = f.read()
    return config.model_copy(
        update={
            "persona_path": str(persona_path),
            "persona_content": persona_content,
        }
    )
