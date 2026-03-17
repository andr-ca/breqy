from __future__ import annotations
import json
from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult


class QaAutomationAdapter(AgentAdapter):
    role = "qa_automation"

    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        return self._load_template() + f"\n\n## Task: {task.task_id} — {task.title}"

    def parse_output(self, result: RunResult) -> ParsedOutput:
        try:
            data = json.loads(result.output)
            return ParsedOutput(
                status=data.get("status", "fail"),
                artifact_paths=[],
                failure_source=data.get("failure_source"),
                notes=data.get("notes", ""),
            )
        except (json.JSONDecodeError, KeyError):
            return ParsedOutput(status="fail", artifact_paths=[], notes=result.output[:200])
