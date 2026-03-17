from __future__ import annotations
from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext, _parse_generic
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.task_envelope import TaskEnvelope
from system.orchestrator.schemas.run_result import RunResult


class PlannerAdapter(AgentAdapter):
    role = "planner"

    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        return (
            self._load_template()
            + f"\n\n## Task Envelope\n"
            + f"task_id: {task.task_id}\ntitle: {task.title}\n"
            + f"description: {task.description}\n"
            + f"acceptance_criteria:\n" + "\n".join(f"  - {c}" for c in task.acceptance_criteria)
        )

    def parse_output(self, result: RunResult) -> ParsedOutput:
        return _parse_generic(result)
