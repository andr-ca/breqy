from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    summary: str = ""


class ApprovalRequestSpec(BaseModel):
    description: str
    grant_key: str = ""


class ToolExecutor(ABC):
    name: str = ""
    description: str = ""
    input_schema: ClassVar[dict[str, object]] = {}

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    def approval_request_spec(self, arguments: dict[str, Any]) -> ApprovalRequestSpec | None:
        return None

    async def close(self) -> None:
        return None
