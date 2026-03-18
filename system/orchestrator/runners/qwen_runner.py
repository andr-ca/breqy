from __future__ import annotations
import subprocess
import os
from system.orchestrator.runners.base import AgentRunner
from system.orchestrator.schemas.run_result import RunContext
from system.orchestrator.auth.credential_store import CredentialStore

_PROVIDER_NAME = "qwen"
_ENV_KEY = "DASHSCOPE_API_KEY"


class QwenRunner(AgentRunner):
    """Qwen runner. Requires DASHSCOPE_API_KEY in environment."""

    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self._store = credential_store

    def start(self, prompt: str, context: RunContext) -> subprocess.Popen:
        env = {**os.environ, **context.extra_env}
        if self._store:
            token = self._store.get(_PROVIDER_NAME)
            if token:
                env[_ENV_KEY] = token
        return subprocess.Popen(
            ["qwen", prompt], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=context.work_dir, env=env,
        )
