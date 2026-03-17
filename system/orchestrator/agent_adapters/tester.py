from __future__ import annotations
from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext, _parse_generic
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult


class TesterAdapter(AgentAdapter):
    role = "tester"

    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        return self._load_template() + f"\n\n## Task: {task.task_id} — {task.title}"

    def parse_output(self, result: RunResult) -> ParsedOutput:
        return _parse_generic(result)
