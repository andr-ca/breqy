from __future__ import annotations

import os
import subprocess

from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult
from system.orchestrator.session_manager import is_rate_limit_output


class ClaudeRunner(AgentRunner):
    def run(self, prompt: str, context: RunContext) -> RunResult:
        cmd = [
            "claude", "-p", prompt,
            "--output-format", "stream-json",
            "--permission-mode", "acceptEdits",
        ]
        if context.session_id:
            cmd += ["--resume", context.session_id]

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=self._env(context),
        )
        self.proc = proc
        output_lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            output_lines.append(line)
        proc.wait()
        output = "".join(output_lines)

        if is_rate_limit_output(output):
            return RunResult(status="rate_limited", output=output, exit_code=proc.returncode)
        if proc.returncode != 0:
            return RunResult(status="failed", output=output, exit_code=proc.returncode)
        return RunResult(status="completed", output=output, exit_code=0)

    def _env(self, context: RunContext) -> dict[str, str]:
        env = os.environ.copy()
        env.update(context.extra_env)
        return env
