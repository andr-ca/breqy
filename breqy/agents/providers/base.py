"""Breqy-owned model provider contracts."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator, Literal

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, object] = Field(default_factory=dict)


class ProviderRequest(BaseModel):
    prompt: str
    work_dir: Path
    session_id: str | None = None
    tools: list[ToolDefinition] = Field(default_factory=list)
    extra_env: dict[str, str] = Field(default_factory=dict)


class ToolCallDelta(BaseModel):
    call_id: str
    tool_name: str
    arguments_chunk: str = ""


class CompletionMetadata(BaseModel):
    provider_id: str
    model_id: str
    exit_code: int
    session_id: str | None = None
    duration_seconds: float | None = None
    cost_usd: float | None = None


class ProviderEvent(BaseModel):
    kind: Literal["text", "tool_call", "complete"]
    text: str | None = None
    tool_call: ToolCallDelta | None = None
    metadata: CompletionMetadata | None = None


class ModelProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @property
    @abstractmethod
    def model_id(self) -> str: ...

    @property
    @abstractmethod
    def supports_tool_calls(self) -> bool: ...

    @abstractmethod
    def stream(self, request: ProviderRequest) -> Iterator[ProviderEvent]: ...
