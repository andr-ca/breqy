"""Configuration models for engine and agent."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from breqy.domain.models import FilesystemPolicy, PolicyRule


SUPPORTED_AGENT_PROVIDERS = {"copilot", "codex", "claude", "gemini", "qwen"}


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    id: str
    transport: Literal["process"]
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    startup_timeout_seconds: float = Field(default=10.0, gt=0)
    request_timeout_seconds: float = Field(default=30.0, gt=0)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("MCP server id must not be empty")
        if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in normalized):
            raise ValueError(
                "MCP server id must contain only lowercase letters, digits, and hyphens"
            )
        return normalized


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
    policy_rules: list[PolicyRule] = Field(default_factory=list)
    filesystem_policies: list[FilesystemPolicy] = Field(default_factory=list)

    @model_validator(mode="after")
    def expand_paths(self) -> EngineConfig:
        """Expand ~ and environment variables in all path fields."""
        for field_name in ("socket_path", "data_dir", "db_path"):
            raw = getattr(self, field_name)
            expanded = str(Path(os.path.expandvars(os.path.expanduser(raw))).resolve())
            object.__setattr__(self, field_name, expanded)
        return self

    @property
    def log_dir(self) -> str:
        """Log directory derived from data_dir."""
        return str(Path(self.data_dir) / "logs")


class AgentConfig(BaseModel):
    """Agent process configuration loaded from agent.yaml."""

    id: str
    name: str
    provider: str
    model: str
    display_name: str = ""
    port: int | None = None
    engine_socket: str = Field(
        default_factory=lambda: os.getenv("BREQY_ENGINE_SOCKET", "/tmp/breqy-engine.sock")
    )
    persona_file: str = "persona.md"
    persona_path: str | None = None
    persona_content: str | None = None
    autonomy_level: str = "supervised"
    tool_permissions: list[str] = Field(default_factory=list)
    skill_permissions: list[str] = Field(default_factory=list)
    provider_settings: dict[str, str] = Field(default_factory=dict)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    log_level: str = "INFO"
    log_path: str | None = None

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in SUPPORTED_AGENT_PROVIDERS:
            supported = ", ".join(sorted(SUPPORTED_AGENT_PROVIDERS))
            raise ValueError(f"provider must be one of: {supported}")
        return normalized

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("model must not be empty")
        return normalized

    @field_validator("skill_permissions")
    @classmethod
    def validate_skill_permissions(cls, value: list[str]) -> list[str]:
        normalized = [permission.strip() for permission in value]
        if any(not permission for permission in normalized):
            raise ValueError("skill permissions must not be empty")
        if "*" in normalized:
            if normalized != ["*"]:
                raise ValueError("skill permissions wildcard must be ['*']")
            return ["*"]
        return normalized
