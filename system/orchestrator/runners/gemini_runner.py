from __future__ import annotations
import subprocess
import os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult

_PROVIDER_NAME = "gemini"
_ENV_KEY = "GOOGLE_API_KEY"


class GeminiRunner(AgentRunner):
    def __init__(self, credential_store=None) -> None:
        self._store = credential_store

    def run(self, prompt: str, context: RunContext) -> RunResult:
        env = {**os.environ, **context.extra_env}
        if self._store:
            token = self._store.get(_PROVIDER_NAME)
            if token:
                env[_ENV_KEY] = token
        proc = subprocess.Popen(
            ["gemini", prompt], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
        raw = proc.stdout
        output: str = raw.read() if hasattr(raw, "read") else (raw or "")
        proc.wait()
        status = "completed" if proc.returncode == 0 else "failed"
        return RunResult(status=status, output=output, exit_code=proc.returncode)
