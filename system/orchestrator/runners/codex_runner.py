from __future__ import annotations
import subprocess
import os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext
from system.orchestrator.auth.credential_store import CredentialStore

_PROVIDER_NAME = "codex"
_ENV_KEY = "OPENAI_API_KEY"


class CodexRunner(AgentRunner):
    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self._store = credential_store

    def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
        env = {**os.environ, **context.extra_env}
        if self._store:
            token = self._store.get(_PROVIDER_NAME)
            if token:
                env[_ENV_KEY] = token
        return subprocess.Popen(
            ["codex", prompt], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
