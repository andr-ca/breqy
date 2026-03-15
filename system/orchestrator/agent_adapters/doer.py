from __future__ import annotations

from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext, _parse_generic
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.run_result import RunResult
from system.orchestrator.schemas.task_envelope import TaskEnvelope


class DoerAdapter(AgentAdapter):
    role = "doer"

    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        parts = [self._load_template(), f"\n\n## Task: {task.task_id} — {task.title}"]
        if task.acceptance_criteria:
            parts.append("\n## Acceptance Criteria")
            parts.extend(f"- {c}" for c in task.acceptance_criteria)
        if context.rework_count > 0 and context.failure_notes:
            parts.append(f"\n## Rework Notes (iteration {context.rework_count})")
            parts.append(context.failure_notes)
        return "\n".join(parts)

    def parse_output(self, result: RunResult) -> ParsedOutput:
        return _parse_generic(result)
