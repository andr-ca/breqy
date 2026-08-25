from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod

from system.orchestrator.schemas.run_result import RunContext, RunResult, RunStatus


class AgentRunner(ABC):
    @abstractmethod
    def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
        """Start the agent subprocess and return without waiting."""
        ...

    def run(self, prompt: str, context: RunContext) -> RunResult:
        """Default implementation: start() + communicate(). Override for custom logic."""
        proc = self.start(prompt, context)
        output, _ = proc.communicate()
        status: RunStatus = "completed" if proc.returncode == 0 else "failed"
        return RunResult(status=status, output=output, exit_code=proc.returncode)
