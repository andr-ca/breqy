"""Configuration models for engine and agent."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    id: str
    transport: Literal["process"]
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    startup_timeout_seconds: float = Field(default=10.0, gt=0)
    request_timeout_seconds: float = Field(default=30.0, gt=0)


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
    engine_socket: str = Field(
        default_factory=lambda: os.getenv("BREQY_ENGINE_SOCKET", "/tmp/breqy-engine.sock")
    )
    persona_file: str = "persona.md"
    autonomy_level: str = "supervised"
    tool_permissions: list[str] = Field(default_factory=list)
    skill_permissions: list[str] = Field(default_factory=list)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    log_level: str = "INFO"
    log_path: str | None = None
