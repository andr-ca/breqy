from __future__ import annotations
from abc import ABC, abstractmethod
from system.orchestrator.schemas.run_result import RunContext, RunResult


class AgentRunner(ABC):
    @abstractmethod
    def run(self, prompt: str, context: RunContext) -> RunResult:
        """Spawn subprocess, stream output, handle rate limits, return result."""
        ...
