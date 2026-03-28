"""Breqy-native provider adapters over class-based orchestrator runner reuse."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from breqy.agents.credentials import CredentialStore
from breqy.agents.providers.base import (
    CompletionMetadata,
    ModelProvider,
    ProviderEvent,
    ProviderRequest,
    ToolDefinition,
    ToolCallDelta,
)
from system.orchestrator.auth.credential_store import CredentialStore as OrchestratorCredentialStore
from system.orchestrator.runners.claude_runner import ClaudeRunner
from system.orchestrator.runners.codex_runner import CodexRunner
from system.orchestrator.runners.gemini_runner import GeminiRunner
from system.orchestrator.runners.qwen_runner import QwenRunner
from system.orchestrator.schemas.run_result import RunContext

_PROVIDER_AUTH_ENV_VARS = {
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "DASHSCOPE_API_KEY",
}

_PASSTHROUGH_ENV_VARS = {
    "COLORTERM",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "NO_COLOR",
    "PATH",
    "SHELL",
    "TERM",
    "TMP",
    "TEMP",
    "TMPDIR",
    "USER",
}

_ISOLATED_CONFIG_ENV_VARS = {
    "GH_CONFIG_DIR": "gh",
    "OPENAI_CONFIG_DIR": "openai",
    "ANTHROPIC_CONFIG_DIR": "anthropic",
}


def _isolated_runtime_env(*, extra_env: dict[str, str], provider_id: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key in _PASSTHROUGH_ENV_VARS
    }
    for env_var in _PROVIDER_AUTH_ENV_VARS:
        env.pop(env_var, None)
    runtime_root = Path(tempfile.mkdtemp(prefix=f"breqy-provider-{provider_id}-"))
    home_dir = runtime_root / "home"
    config_dir = runtime_root / "config"
    home_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home_dir)
    env["XDG_CONFIG_HOME"] = str(config_dir)
    for env_var, leaf in _ISOLATED_CONFIG_ENV_VARS.items():
        isolated_dir = runtime_root / leaf
        isolated_dir.mkdir(parents=True, exist_ok=True)
        env[env_var] = str(isolated_dir)
    env.update(extra_env)
    env["HOME"] = str(home_dir)
    env["XDG_CONFIG_HOME"] = str(config_dir)
    for env_var, leaf in _ISOLATED_CONFIG_ENV_VARS.items():
        env[env_var] = str(runtime_root / leaf)
    return env


def _extract_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value.get("type") == "text":
            text = value.get("text")
            return text if isinstance(text, str) else ""
        content = value.get("content")
        if isinstance(content, list):
            parts = [_extract_text(item) for item in content]
            return "".join(part for part in parts if part)
        message = value.get("message")
        if message is not None:
            return _extract_text(message)
        text = value.get("text")
        return text if isinstance(text, str) else ""
    if isinstance(value, list):
        return "".join(_extract_text(item) for item in value)
    return ""


@dataclass(frozen=True)
class _RunnerInvocation:
    prompt: str
    work_dir: Path
    session_id: str | None
    model_id: str
    tools: list[ToolDefinition]
    extra_env: dict[str, str]


class _RunnerCredentialStore(OrchestratorCredentialStore):
    """Adapter from Breqy structured credentials to orchestrator token store."""

    def __init__(self, credential_store: CredentialStore) -> None:
        self._credential_store = credential_store

    def get(self, provider: str) -> str | None:
        credential = self._credential_store.get(provider)
        if credential is None:
            return None
        return credential.secret_value.get_secret_value()

    def set(self, provider: str, token: str) -> None:
        raise NotImplementedError("runner credential writes are not supported in Breqy adapters")

    def delete(self, provider: str) -> None:
        raise NotImplementedError("runner credential deletes are not supported in Breqy adapters")


class _ConfiguredRunContext(RunContext):
    model_id: str
    tools: list[ToolDefinition] = []


class _SafeClaudeRunner(ClaudeRunner):
    def start(self, prompt: str, context: RunContext):
        configured = _ConfiguredRunContext.model_validate(context.model_dump())
        cmd = [
            "claude",
            "-p",
            prompt,
            "--model",
            configured.model_id,
            "--output-format",
            "stream-json",
        ]
        if configured.session_id:
            cmd += ["--resume", configured.session_id]
        for tool in configured.tools:
            cmd += ["--allowedTools", tool.name]
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=configured.work_dir,
            env=self._env(configured),
        )

    def _env(self, context: RunContext) -> dict[str, str]:
        env = _isolated_runtime_env(extra_env=context.extra_env, provider_id="claude")
        if self._store:
            token = self._store.get("claude")
            if token:
                env["ANTHROPIC_API_KEY"] = token
        return env


def _start_configured_chat_runner(
    runner: Any,
    *,
    provider_name: str,
    provider_env_var: str,
    command_prefix: list[str],
    prompt: str,
    context: RunContext,
):
    configured = _ConfiguredRunContext.model_validate(context.model_dump())
    env = _isolated_runtime_env(extra_env=configured.extra_env, provider_id=provider_name)
    store = getattr(runner, "_store", None)
    if store:
        token = store.get(provider_name)
        if token:
            env[provider_env_var] = token
    return subprocess.Popen(
        [*command_prefix, "--model", configured.model_id, prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=configured.work_dir,
        env=env,
    )


class _ConfiguredCodexRunner(CodexRunner):
    def start(self, prompt: str, context: RunContext):
        return _start_configured_chat_runner(
            self,
            provider_name="codex",
            provider_env_var="OPENAI_API_KEY",
            command_prefix=["codex"],
            prompt=prompt,
            context=context,
        )


class _ConfiguredGeminiRunner(GeminiRunner):
    def start(self, prompt: str, context: RunContext):
        return _start_configured_chat_runner(
            self,
            provider_name="gemini",
            provider_env_var="GOOGLE_API_KEY",
            command_prefix=["gemini"],
            prompt=prompt,
            context=context,
        )


class _ConfiguredQwenRunner(QwenRunner):
    def start(self, prompt: str, context: RunContext):
        return _start_configured_chat_runner(
            self,
            provider_name="qwen",
            provider_env_var="DASHSCOPE_API_KEY",
            command_prefix=["qwen"],
            prompt=prompt,
            context=context,
        )


class _RunnerFactory:
    """Internal shim that owns class-based runner reuse and translation."""

    def __init__(self, credential_store: CredentialStore) -> None:
        self._credential_store = credential_store

    def _runner_store(self) -> _RunnerCredentialStore:
        return _RunnerCredentialStore(self._credential_store)

    def make_claude_runner(self) -> _SafeClaudeRunner:
        return _SafeClaudeRunner(credential_store=self._runner_store())

    def make_codex_runner(self) -> _ConfiguredCodexRunner:
        return _ConfiguredCodexRunner(credential_store=self._runner_store())

    def make_gemini_runner(self) -> _ConfiguredGeminiRunner:
        return _ConfiguredGeminiRunner(credential_store=self._runner_store())

    def make_qwen_runner(self) -> _ConfiguredQwenRunner:
        return _ConfiguredQwenRunner(credential_store=self._runner_store())

    def run_context_from_invocation(self, invocation: _RunnerInvocation) -> _ConfiguredRunContext:
        return _ConfiguredRunContext(
            task_id="breqy-provider-stream",
            role="provider",
            work_dir=invocation.work_dir,
            session_id=invocation.session_id,
            extra_env=invocation.extra_env,
            model_id=invocation.model_id,
            tools=invocation.tools,
        )

    def invocation_from_request(
        self,
        request: ProviderRequest,
        *,
        model_id: str,
        allow_tools: bool,
    ) -> _RunnerInvocation:
        extra_env = dict(request.extra_env)
        for env_var in _PROVIDER_AUTH_ENV_VARS:
            extra_env.pop(env_var, None)
        return _RunnerInvocation(
            prompt=request.prompt,
            work_dir=request.work_dir,
            session_id=request.session_id,
            model_id=model_id,
            tools=list(request.tools) if allow_tools else [],
            extra_env=extra_env,
        )


class _BaseRunnerProvider(ModelProvider):
    def __init__(
        self,
        *,
        provider_id: str,
        model_id: str,
        runner: Any,
        runner_factory: _RunnerFactory,
    ) -> None:
        self._provider_id = provider_id
        self._model_id = model_id
        self._runner = runner
        self._runner_factory = runner_factory

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def model_id(self) -> str:
        return self._model_id

    def _run_context(self, request: ProviderRequest, *, allow_tools: bool) -> _ConfiguredRunContext:
        invocation = self._runner_factory.invocation_from_request(
            request,
            model_id=self.model_id,
            allow_tools=allow_tools,
        )
        return self._runner_factory.run_context_from_invocation(invocation)


class _ChatOnlyRunnerProvider(_BaseRunnerProvider):
    @property
    def supports_tool_calls(self) -> bool:
        return False

    def stream(self, request: ProviderRequest) -> Iterator[ProviderEvent]:
        proc: Any = self._runner.start(request.prompt, self._run_context(request, allow_tools=False))
        if proc.stdout is not None:
            for raw_line in proc.stdout:
                line = raw_line.rstrip("\r\n")
                if line.strip():
                    yield ProviderEvent(kind="text", text=line)
        exit_code = proc.wait()
        yield ProviderEvent(
            kind="complete",
            metadata=CompletionMetadata(
                provider_id=self.provider_id,
                model_id=self.model_id,
                exit_code=exit_code,
            ),
        )


class _ClaudeRunnerProvider(_BaseRunnerProvider):
    @property
    def supports_tool_calls(self) -> bool:
        return True

    def stream(self, request: ProviderRequest) -> Iterator[ProviderEvent]:
        proc: Any = self._runner.start(request.prompt, self._run_context(request, allow_tools=True))
        active_tool_call: ToolCallDelta | None = None

        if proc.stdout is not None:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    exit_code = proc.wait() or 1
                    yield ProviderEvent(
                        kind="complete",
                        metadata=CompletionMetadata(
                            provider_id=self.provider_id,
                            model_id=self.model_id,
                            exit_code=exit_code,
                        ),
                    )
                    return

                event_type = event.get("type")

                if event_type == "assistant":
                    text = _extract_text(event.get("message") or event.get("content_block") or "")
                    if text:
                        yield ProviderEvent(kind="text", text=text)
                    continue

                if event_type == "content_block_start":
                    content_block = event.get("content_block", {})
                    if content_block.get("type") == "tool_use":
                        active_tool_call = ToolCallDelta(
                            call_id=str(content_block.get("id", "")),
                            tool_name=str(content_block.get("name", "")),
                        )
                        yield ProviderEvent(kind="tool_call", tool_call=active_tool_call)
                    continue

                if event_type == "tool_use":
                    active_tool_call = ToolCallDelta(
                        call_id=str(event.get("id", "")),
                        tool_name=str(event.get("name") or event.get("tool", {}).get("name", "")),
                    )
                    yield ProviderEvent(kind="tool_call", tool_call=active_tool_call)
                    continue

                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    text = delta.get("text")
                    if isinstance(text, str) and text:
                        yield ProviderEvent(kind="text", text=text)
                    partial_json = delta.get("partial_json")
                    if (
                        isinstance(partial_json, str)
                        and partial_json
                        and active_tool_call is not None
                    ):
                        yield ProviderEvent(
                            kind="tool_call",
                            tool_call=ToolCallDelta(
                                call_id=active_tool_call.call_id,
                                tool_name=active_tool_call.tool_name,
                                arguments_chunk=partial_json,
                            ),
                        )
                    continue

                if event_type == "result":
                    exit_code = proc.wait()
                    yield ProviderEvent(
                        kind="complete",
                        metadata=CompletionMetadata(
                            provider_id=self.provider_id,
                            model_id=self.model_id,
                            exit_code=exit_code,
                            session_id=event.get("session_id"),
                            duration_seconds=event.get("duration_seconds"),
                            cost_usd=event.get("cost_usd"),
                        ),
                    )
                    return

        exit_code = proc.wait()
        yield ProviderEvent(
            kind="complete",
            metadata=CompletionMetadata(
                provider_id=self.provider_id,
                model_id=self.model_id,
                exit_code=exit_code,
            ),
        )


def build_model_providers(
    *,
    credential_store: CredentialStore,
    model_by_provider: dict[str, str],
) -> dict[str, ModelProvider]:
    runner_factory = _RunnerFactory(credential_store)
    providers: dict[str, ModelProvider] = {}

    for provider_id, model_id in model_by_provider.items():
        if provider_id == "claude":
            providers[provider_id] = _ClaudeRunnerProvider(
                provider_id=provider_id,
                model_id=model_id,
                runner=runner_factory.make_claude_runner(),
                runner_factory=runner_factory,
            )
        elif provider_id == "codex":
            providers[provider_id] = _ChatOnlyRunnerProvider(
                provider_id=provider_id,
                model_id=model_id,
                runner=runner_factory.make_codex_runner(),
                runner_factory=runner_factory,
            )
        elif provider_id == "copilot":
            from breqy.agents.providers.copilot import CopilotProvider
            from breqy.agents.providers.copilot_auth import CopilotAuthenticator
            from breqy.agents.providers.copilot_client import CopilotApiClient

            authenticator = CopilotAuthenticator(credential_store)
            client = CopilotApiClient()
            providers[provider_id] = CopilotProvider(
                model_id=model_id,
                authenticator=authenticator,
                client=client,
            )
        elif provider_id == "gemini":
            providers[provider_id] = _ChatOnlyRunnerProvider(
                provider_id=provider_id,
                model_id=model_id,
                runner=runner_factory.make_gemini_runner(),
                runner_factory=runner_factory,
            )
        elif provider_id == "qwen":
            providers[provider_id] = _ChatOnlyRunnerProvider(
                provider_id=provider_id,
                model_id=model_id,
                runner=runner_factory.make_qwen_runner(),
                runner_factory=runner_factory,
            )
        else:
            message = f"unsupported provider: {provider_id!r}"
            raise ValueError(message)

    return providers
