from __future__ import annotations
import subprocess, os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult


class GeminiRunner(AgentRunner):
    def run(self, prompt: str, context: RunContext) -> RunResult:
        env = {**os.environ, **context.extra_env}
        proc = subprocess.Popen(
            ["gemini", prompt], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
        raw = proc.stdout
        output: str = raw.read() if hasattr(raw, "read") else (raw or "")
        proc.wait()
        status = "completed" if proc.returncode == 0 else "failed"
        return RunResult(status=status, output=output, exit_code=proc.returncode)
