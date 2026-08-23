from __future__ import annotations

from system.orchestrator.agent_adapters.base import AgentAdapter, TaskContext, _parse_generic
from system.orchestrator.schemas.artifacts import ParsedOutput
from system.orchestrator.schemas.run_result import RunResult
from system.orchestrator.schemas.task_envelope import TaskEnvelope


class CheckerAdapter(AgentAdapter):
    role = "checker"

    def build_prompt(self, task: TaskEnvelope, context: TaskContext) -> str:
        parts = [self._load_template(), f"\n\n## Task: {task.task_id}"]
        if "git_diff" in context.prior_artifacts:
            parts.append("\n## Git Diff\n```diff\n" + context.prior_artifacts["git_diff"] + "\n```")
        if "doer_report" in context.prior_artifacts:
            parts.append("\n## Doer Report\n" + context.prior_artifacts["doer_report"])
        return "\n".join(parts)

    def parse_output(self, result: RunResult) -> ParsedOutput:
        return _parse_generic(result)
