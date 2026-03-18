from __future__ import annotations
import subprocess
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext, RunResult
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.session_manager import is_rate_limit_output

_PROVIDER_NAME = "claude"
_ENV_KEY = "ANTHROPIC_API_KEY"


class ClaudeRunner(AgentRunner):
    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self._store = credential_store

    def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
        cmd = [
            "claude", "-p", prompt,
            "--output-format", "stream-json",
            "--permission-mode", "acceptEdits",
        ]
        if context.session_id:
            cmd += ["--resume", context.session_id]
        return subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=self._env(context),
        )

    def run(self, prompt: str, context: RunContext) -> RunResult:
        proc = self.start(prompt, context)
        output, _ = proc.communicate()
        if is_rate_limit_output(output):
            return RunResult(status="rate_limited", output=output, exit_code=proc.returncode)
        if proc.returncode != 0:
            return RunResult(status="failed", output=output, exit_code=proc.returncode)
        return RunResult(status="completed", output=output, exit_code=0)

    def _env(self, context: RunContext) -> dict[str, str]:
        import os
        env = os.environ.copy()
        env.update(context.extra_env)
        if self._store:
            token = self._store.get(_PROVIDER_NAME)
            if token:
                env[_ENV_KEY] = token
        return env
