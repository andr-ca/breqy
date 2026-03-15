from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

RunStatus = Literal["completed", "rate_limited", "failed"]


class RunResult(BaseModel):
    status: RunStatus
    output: str
    exit_code: int
    session_id: str | None = None
    artifacts_written: list[str] = Field(default_factory=list)


class RunContext(BaseModel):
    task_id: str
    role: str
    work_dir: Path
    session_id: str | None = None
    extra_env: dict[str, str] = Field(default_factory=dict)
