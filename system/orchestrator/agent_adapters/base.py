from __future__ import annotations
import json as _json
from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class TaskContext(BaseModel):
    task: TaskEnvelope
    prior_artifacts: dict[str, str]   # name → file path
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


def _parse_generic(result: RunResult) -> ParsedOutput:
    """Default parse: look for {status: pass/fail} JSON in output."""
    try:
        data = _json.loads(result.output)
        return ParsedOutput(
            status=data.get("status", "fail"),
            artifact_paths=data.get("artifact_paths", []),
            notes=data.get("notes", ""),
        )
    except (_json.JSONDecodeError, KeyError):
        status = "pass" if result.exit_code == 0 else "fail"
        return ParsedOutput(status=status, artifact_paths=[], notes=result.output[:200])
