"""Load configuration from YAML files and environment."""
from __future__ import annotations

from pathlib import Path

import yaml

from breqy.config.models import AgentConfig, EngineConfig


def load_engine_config(config_path: str | None = None) -> EngineConfig:
    """Load engine config from env vars, optionally supplemented by YAML."""
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return EngineConfig(**data)
    return EngineConfig()


def load_agent_config(agent_dir: str) -> AgentConfig:
    """Load agent config from agent.yaml in the given directory."""
    config_path = Path(agent_dir) / "agent.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Agent config not found: {config_path}")
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}
    return AgentConfig(**data)
