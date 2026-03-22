"""Configuration dataclasses for engine and agent."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class EngineConfig(BaseModel):
    """Engine daemon configuration."""

    socket_path: str = Field(
        default_factory=lambda: os.getenv(
            "BREQY_ENGINE_SOCKET", "/tmp/breqy-engine.sock"
        )
    )
    data_dir: str = Field(
        default_factory=lambda: os.getenv(
            "BREQY_DATA_DIR", str(Path.home() / ".breqy" / "data")
        )
    )
    db_path: str = Field(
        default_factory=lambda: os.getenv(
            "BREQY_DB_PATH",
            str(Path.home() / ".breqy" / "data" / "breqy.db"),
        )
    )
    log_level: str = Field(
        default_factory=lambda: os.getenv("BREQY_LOG_LEVEL", "INFO")
    )
    default_agent_id: str = "breqy"


class AgentConfig(BaseModel):
    """Agent process configuration loaded from agent.yaml."""

    id: str
    name: str
    display_name: str = ""
    port: int | None = None
    engine_socket: str = "/tmp/breqy-engine.sock"
    persona_file: str = "persona.md"
    autonomy_level: str = "supervised"
    tool_permissions: list[str] = Field(default_factory=list)
    skill_permissions: list[str] = Field(default_factory=list)
    log_level: str = "INFO"
    log_path: str = ""
