from __future__ import annotations

import os
import subprocess

from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult


class QwenRunner(AgentRunner):
    """Qwen runner via Alibaba DashScope CLI (qwen).
    Requires DASHSCOPE_API_KEY in environment.
    Session continuity: TBD — depends on qwen CLI support."""

    def run(self, prompt: str, context: RunContext) -> RunResult:
        env = {**os.environ, **context.extra_env}
        proc = subprocess.Popen(
            ["qwen", prompt], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
        assert proc.stdout is not None
        output = proc.stdout.read()
        proc.wait()
        status = "completed" if proc.returncode == 0 else "failed"
        return RunResult(status=status, output=output, exit_code=proc.returncode)
