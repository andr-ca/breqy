from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel

from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.run_result import RunResult
from system.orchestrator.schemas.task_envelope import TaskEnvelope

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class TaskContext(BaseModel):
    task: TaskEnvelope
    prior_artifacts: dict[str, str]  # name → file path
    rework_count: int = 0
    failure_notes: str = ""


class AgentAdapter(ABC):
    role: str = ""
    prompts_dir: Path = _PROMPTS_DIR

    def _load_template(self) -> str:
        path = self.prompts_dir / f"{self.role}.md"
        if path.exists():
            return path.read_text()
        return f"# {self.role.capitalize()} role\n"

    @abstractmethod
    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str: ...

    @abstractmethod
    def parse_output(self, result: RunResult) -> ParsedOutput: ...
