from __future__ import annotations
import subprocess
import os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult
from system.orchestrator.auth.credential_store import CredentialStore

_PROVIDER_NAME = "gemini"
_ENV_KEY = "GOOGLE_API_KEY"


class GeminiRunner(AgentRunner):
    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self._store = credential_store

    def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
        env = {**os.environ, **context.extra_env}
        if self._store:
            token = self._store.get(_PROVIDER_NAME)
            if token:
                env[_ENV_KEY] = token
        return subprocess.Popen(
            ["gemini", prompt], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )

    def run(self, prompt: str, context: RunContext) -> RunResult:
        proc = self.start(prompt, context)
        output, _ = proc.communicate()
        status = "completed" if proc.returncode == 0 else "failed"
        return RunResult(status=status, output=output, exit_code=proc.returncode)
