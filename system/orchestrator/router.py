from __future__ import annotations
from system.orchestrator.config import OrchestratorConfig
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.runners.claude_runner import ClaudeRunner
from system.orchestrator.runners.codex_runner import CodexRunner
from system.orchestrator.runners.gemini_runner import GeminiRunner
from system.orchestrator.runners.copilot_runner import CopilotRunner
from system.orchestrator.runners.qwen_runner import QwenRunner
from system.orchestrator.agent_adapters.base import AgentAdapter
from system.orchestrator.agent_adapters.planner import PlannerAdapter
from system.orchestrator.agent_adapters.doer import DoerAdapter
from system.orchestrator.agent_adapters.checker import CheckerAdapter
from system.orchestrator.agent_adapters.tester import TesterAdapter
from system.orchestrator.agent_adapters.qa_automation import QaAutomationAdapter
from system.orchestrator.agent_adapters.lessons import LessonsAdapter

_RUNNERS: dict[str, type[AgentRunner]] = {
    "claude": ClaudeRunner,
    "codex": CodexRunner,
    "gemini": GeminiRunner,
    "copilot": CopilotRunner,
    "qwen": QwenRunner,
}

_ADAPTERS: dict[str, type[AgentAdapter]] = {
    "planner": PlannerAdapter,
    "doer": DoerAdapter,
    "checker": CheckerAdapter,
    "tester": TesterAdapter,
    "qa_automation": QaAutomationAdapter,
    "lessons": LessonsAdapter,
}


class Router:
    def __init__(self, config: OrchestratorConfig) -> None:
        self._config = config

    def resolve(
        self, task_type: str, component: str, role: str
    ) -> tuple[AgentRunner, AgentAdapter]:
        if role not in _ADAPTERS:
            raise ValueError(f"Unknown role: {role}")
        agent_type = (
            self._config.routing_rules
            .get(task_type, {})
            .get(component, {})
            .get(role)
            or self._config.agent_defaults.get(role, "claude")
        )
        runner_cls = _RUNNERS.get(agent_type, ClaudeRunner)
        adapter_cls = _ADAPTERS[role]
        return runner_cls(), adapter_cls()
