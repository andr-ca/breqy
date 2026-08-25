"""Tests for Breqy-native provider execution adapters."""
from __future__ import annotations

import io
import json
import os
from typing import cast

import pytest
from typing import Any
from unittest.mock import MagicMock

from pydantic import SecretStr

from breqy.agents.credentials import CredentialStore
from breqy.agents.models import ProviderCredential
from breqy.domain.enums import CredentialKind
from breqy.secrets.provider import SecretProvider
from breqy.agents.providers.adapters import _RunnerCredentialStore, _extract_text, build_model_providers
from breqy.agents.providers.base import ModelProvider, ProviderRequest, ToolDefinition


class MemorySecretProvider(SecretProvider):
    """In-memory secret provider for unit tests."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


class FakeProcess:
    def __init__(self, stdout_text: str, returncode: int = 0) -> None:
        self.stdout = io.StringIO(stdout_text)
        self.returncode = returncode
        self.waited = False

    def wait(self) -> int:
        self.waited = True
        return self.returncode


class StreamingStdout:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def __iter__(self):
        return iter(self._chunks)


class FakeStreamingProcess:
    def __init__(self, chunks: list[str], returncode: int = 0) -> None:
        self.stdout = StreamingStdout(chunks)
        self.returncode = returncode
        self.waited = False

    def wait(self) -> int:
        self.waited = True
        return self.returncode


def _credential(provider: str, secret: str) -> ProviderCredential:
    return ProviderCredential(
        provider=provider,
        credential_kind=CredentialKind.ACCESS_TOKEN,
        secret_value=SecretStr(secret),
    )


def test_build_model_providers_exposes_supported_provider_and_model_identity() -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={
            "claude": "claude-3-7-sonnet",
            "copilot": "gpt-4o-mini",
            "codex": "gpt-5-codex",
            "gemini": "gemini-2.5-pro",
            "qwen": "qwen-max",
        },
    )

    assert set(providers) == {"claude", "copilot", "codex", "gemini", "qwen"}
    assert providers["claude"].provider_id == "claude"
    assert providers["claude"].model_id == "claude-3-7-sonnet"
    assert providers["claude"].supports_tool_calls is True
    assert providers["copilot"].provider_id == "copilot"
    assert providers["copilot"].model_id == "gpt-4o-mini"
    assert providers["copilot"].supports_tool_calls is True
    assert providers["codex"].provider_id == "codex"
    assert providers["gemini"].provider_id == "gemini"
    assert providers["qwen"].provider_id == "qwen"


def test_claude_adapter_normalizes_text_tool_call_deltas_and_completion(monkeypatch, tmp_path) -> None:
    secret_provider = MemorySecretProvider()
    credential_store = CredentialStore(secret_provider)
    credential_store.set("claude", _credential("claude", "claude-secret"))
    providers = build_model_providers(
        credential_store=credential_store,
        model_by_provider={"claude": "claude-3-7-sonnet"},
    )
    stdout_text = "\n".join(
        [
            json.dumps({
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Hello"}]},
            }),
            json.dumps({
                "type": "content_block_start",
                "content_block": {"type": "tool_use", "id": "toolu_1", "name": "shell", "input": {}},
            }),
            json.dumps({
                "type": "content_block_delta",
                "delta": {"type": "input_json_delta", "partial_json": '{"command":"ls'},
            }),
            json.dumps({
                "type": "content_block_delta",
                "delta": {"type": "input_json_delta", "partial_json": ' -la"}'},
            }),
            json.dumps({
                "type": "content_block_delta",
                "delta": {"text": " world"},
            }),
            json.dumps({
                "type": "result",
                "session_id": "sess-123",
                "duration_seconds": 4,
                "cost_usd": 0.12,
            }),
            "",
        ]
    )

    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeProcess(stdout_text)

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    events = list(
        providers["claude"].stream(
            ProviderRequest(
                prompt="Use the shell tool if needed.",
                work_dir=tmp_path,
            )
        )
    )

    assert [event.text for event in events if event.kind == "text"] == ["Hello", " world"]
    tool_events = [event.tool_call for event in events if event.kind == "tool_call"]
    assert tool_events[0] is not None
    assert tool_events[0].call_id == "toolu_1"
    assert tool_events[0].tool_name == "shell"
    assert [tool_event.arguments_chunk for tool_event in tool_events[1:] if tool_event is not None] == [
        '{"command":"ls',
        ' -la"}',
    ]
    completion = next(event for event in events if event.kind == "complete")
    assert completion.metadata is not None
    assert completion.metadata.session_id == "sess-123"
    assert completion.metadata.exit_code == 0
    assert "stream-json" in captured["cmd"]
    assert "--permission-mode" not in captured["cmd"]
    assert "acceptEdits" not in captured["cmd"]
    assert captured["kwargs"]["env"]["ANTHROPIC_API_KEY"] == "claude-secret"


def test_chat_only_provider_ignores_tools_and_emits_no_tool_call_events(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"gemini": "gemini-2.5-pro"},
    )

    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *args, **kwargs: FakeProcess("plain text response\n"),
    )

    events = list(
        providers["gemini"].stream(
            ProviderRequest(
                prompt="Say hello.",
                work_dir=tmp_path,
                tools=[
                    ToolDefinition(
                        name="shell",
                        description="run shell commands",
                        input_schema={"type": "object"},
                    )
                ],
            )
        )
    )

    assert providers["gemini"].supports_tool_calls is False
    assert [event.text for event in events if event.kind == "text"] == ["plain text response"]
    assert [event for event in events if event.kind == "tool_call"] == []


def test_chat_only_provider_streams_text_before_process_completion(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"gemini": "gemini-2.5-pro"},
    )
    process = FakeStreamingProcess(["hello\n", "world\n"])

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: process)

    stream = providers["gemini"].stream(
        ProviderRequest(
            prompt="Stream hello world.",
            work_dir=tmp_path,
        )
    )

    first_event = next(stream)

    assert first_event.kind == "text"
    assert first_event.text == "hello"
    assert process.waited is False

    remaining_events = list(stream)

    assert [event.text for event in remaining_events if event.kind == "text"] == ["world"]
    assert process.waited is True


def test_chat_only_provider_injects_credentials_from_credential_store(monkeypatch, tmp_path) -> None:
    secret_provider = MemorySecretProvider()
    credential_store = CredentialStore(secret_provider)
    credential_store.set("codex", _credential("codex", "openai-secret"))
    providers = build_model_providers(
        credential_store=credential_store,
        model_by_provider={"codex": "gpt-5-codex"},
    )

    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeProcess("done\n")

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    list(
        providers["codex"].stream(
            ProviderRequest(
                prompt="Hello",
                work_dir=tmp_path,
            )
        )
    )

    assert captured["kwargs"]["env"]["OPENAI_API_KEY"] == "openai-secret"


def test_provider_adapters_wrap_orchestrator_runners(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={
            "claude": "claude-3-7-sonnet",
            "gemini": "gemini-2.5-pro",
        },
    )

    claude_start = MagicMock(
        return_value=FakeProcess(
            "\n".join(
                [
                    json.dumps({"type": "assistant", "message": "hi"}),
                    json.dumps({"type": "result", "session_id": "sess-1"}),
                    "",
                ]
            )
        )
    )
    gemini_start = MagicMock(return_value=FakeStreamingProcess(["chunk one\n", "chunk two\n"]))

    monkeypatch.setattr(cast(Any, providers["claude"])._runner, "start", claude_start)
    monkeypatch.setattr(cast(Any, providers["gemini"])._runner, "start", gemini_start)

    claude_events = list(
        providers["claude"].stream(
            ProviderRequest(prompt="Hello", work_dir=tmp_path, session_id="sess-existing")
        )
    )
    gemini_events = list(
        providers["gemini"].stream(
            ProviderRequest(prompt="Hello", work_dir=tmp_path)
        )
    )

    assert claude_start.call_count == 1
    assert gemini_start.call_count == 1
    assert claude_start.call_args.args[0] == "Hello"
    assert claude_start.call_args.args[1].session_id == "sess-existing"
    assert gemini_start.call_args.args[0] == "Hello"
    assert gemini_start.call_args.args[1].work_dir == tmp_path
    assert [event.text for event in claude_events if event.kind == "text"] == ["hi"]
    assert [event.text for event in gemini_events if event.kind == "text"] == ["chunk one", "chunk two"]


def test_claude_adapter_handles_malformed_stdout_without_raising(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"claude": "claude-3-7-sonnet"},
    )
    process = FakeProcess("not-json\n")

    monkeypatch.setattr(cast(Any, providers["claude"])._runner, "start", MagicMock(return_value=process))

    events = list(
        providers["claude"].stream(
            ProviderRequest(
                prompt="Hello",
                work_dir=tmp_path,
            )
        )
    )

    completion = next(event for event in events if event.kind == "complete")

    assert [event for event in events if event.kind == "text"] == []
    assert completion.metadata is not None
    assert completion.metadata.exit_code == 1
    assert completion.metadata.session_id is None


def test_provider_module_keeps_runner_factory_boundary_internal() -> None:
    from breqy.agents.providers import adapters

    assert hasattr(adapters, "_RunnerFactory")


def test_runner_credential_store_rejects_writes_and_deletes() -> None:
    store = _RunnerCredentialStore(CredentialStore(MemorySecretProvider()))

    with pytest.raises(NotImplementedError, match="writes"):
        store.set("claude", "token")
    with pytest.raises(NotImplementedError, match="deletes"):
        store.delete("claude")


def test_extract_text_handles_nested_message_shapes() -> None:
    assert _extract_text({"message": {"content": [{"type": "text", "text": "hello"}, " world"]}}) == "hello world"
    assert _extract_text([{"text": "alpha"}, {"type": "text", "text": "beta"}]) == "alphabeta"
    assert _extract_text([1, {"text": "ok"}]) == "ok"


def test_claude_adapter_propagates_requested_tools_into_invocation(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"claude": "claude-3-7-sonnet"},
    )
    claude_start = MagicMock(
        return_value=FakeProcess(
            "\n".join(
                [
                    json.dumps({"type": "result", "session_id": "sess-tools"}),
                    "",
                ]
            )
        )
    )
    tools = [
        ToolDefinition(
            name="shell",
            description="run shell commands",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
        )
    ]

    monkeypatch.setattr(cast(Any, providers["claude"])._runner, "start", claude_start)

    list(
        providers["claude"].stream(
            ProviderRequest(
                prompt="Use a tool if needed.",
                work_dir=tmp_path,
                tools=tools,
            )
        )
    )

    invocation = claude_start.call_args.args[1]

    assert invocation.tools == tools


def test_claude_adapter_passes_resume_session_and_allowed_tools_to_subprocess(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"claude": "claude-3-7-sonnet"},
    )
    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProcess("\n".join([json.dumps({"type": "result", "session_id": "sess-1"}), ""]))

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    list(
        providers["claude"].stream(
            ProviderRequest(
                prompt="Resume and use tools.",
                work_dir=tmp_path,
                session_id="sess-existing",
                tools=[ToolDefinition(name="shell", description="run shell", input_schema={"type": "object"})],
            )
        )
    )

    assert "--resume" in captured["cmd"]
    assert "sess-existing" in captured["cmd"]
    assert "--allowedTools" in captured["cmd"]
    assert "shell" in captured["cmd"]


def test_claude_adapter_emits_tool_use_event_shape(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"claude": "claude-3-7-sonnet"},
    )
    process = FakeProcess(
        "\n".join(
            [
                json.dumps({"type": "tool_use", "id": "toolu_2", "name": "filesystem"}),
                json.dumps({"type": "result", "session_id": "sess-tool-use"}),
                "",
            ]
        )
    )

    monkeypatch.setattr(cast(Any, providers["claude"])._runner, "start", MagicMock(return_value=process))

    events = list(providers["claude"].stream(ProviderRequest(prompt="Hi", work_dir=tmp_path)))

    tool_event = next(event for event in events if event.kind == "tool_call")
    assert tool_event.tool_call is not None
    assert tool_event.tool_call.call_id == "toolu_2"
    assert tool_event.tool_call.tool_name == "filesystem"


def test_claude_adapter_emits_completion_when_stream_ends_without_result(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"claude": "claude-3-7-sonnet"},
    )
    process = FakeProcess(json.dumps({"type": "assistant", "message": "hi"}) + "\n")

    monkeypatch.setattr(cast(Any, providers["claude"])._runner, "start", MagicMock(return_value=process))

    events = list(providers["claude"].stream(ProviderRequest(prompt="Hi", work_dir=tmp_path)))

    completion = next(event for event in events if event.kind == "complete")
    assert completion.metadata is not None
    assert completion.metadata.exit_code == 0


def test_qwen_adapter_launches_expected_command(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"qwen": "qwen-model"},
    )
    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProcess("done\n")

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    list(providers["qwen"].stream(ProviderRequest(prompt="Hello", work_dir=tmp_path)))

    assert captured["cmd"][:1] == ["qwen"]


def test_build_model_providers_rejects_unsupported_provider() -> None:
    with pytest.raises(ValueError, match="unsupported provider"):
        build_model_providers(
            credential_store=CredentialStore(MemorySecretProvider()),
            model_by_provider={"openai": "gpt-4o"},
        )


def test_claude_adapter_ignores_blank_lines_in_stream(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"claude": "claude-3-7-sonnet"},
    )
    process = FakeProcess("\n\n" + json.dumps({"type": "result", "session_id": "sess-1"}) + "\n")

    monkeypatch.setattr(cast(Any, providers["claude"])._runner, "start", MagicMock(return_value=process))

    events = list(providers["claude"].stream(ProviderRequest(prompt="Hi", work_dir=tmp_path)))

    assert [event for event in events if event.kind == "text"] == []


def test_chat_only_provider_tools_remain_ignored_by_invocation(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"gemini": "gemini-2.5-pro"},
    )
    gemini_start = MagicMock(return_value=FakeStreamingProcess(["hello\n"]))
    tools = [
        ToolDefinition(
            name="shell",
            description="run shell commands",
            input_schema={"type": "object"},
        )
    ]

    monkeypatch.setattr(cast(Any, providers["gemini"])._runner, "start", gemini_start)

    list(
        providers["gemini"].stream(
            ProviderRequest(
                prompt="Hello",
                work_dir=tmp_path,
                tools=tools,
            )
        )
    )

    invocation = gemini_start.call_args.args[1]

    assert invocation.tools == []


def test_claude_adapter_does_not_leak_ambient_provider_auth_env(monkeypatch, tmp_path) -> None:
    credential_store = CredentialStore(MemorySecretProvider())
    credential_store.set("claude", _credential("claude", "claude-store-secret"))
    providers = build_model_providers(
        credential_store=credential_store,
        model_by_provider={"claude": "claude-3-7-sonnet"},
    )
    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return FakeProcess("\n".join([json.dumps({"type": "result"}), ""]))

    monkeypatch.setenv("ANTHROPIC_API_KEY", "ambient-secret")
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    list(
        providers["claude"].stream(
            ProviderRequest(prompt="Hello", work_dir=tmp_path)
        )
    )

    assert captured["kwargs"]["env"]["ANTHROPIC_API_KEY"] == "claude-store-secret"


def test_chat_only_adapter_does_not_leak_ambient_provider_auth_env(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"gemini": "gemini-2.5-pro"},
    )
    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return FakeProcess("done\n")

    monkeypatch.setenv("GOOGLE_API_KEY", "ambient-gemini-secret")
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    list(
        providers["gemini"].stream(
            ProviderRequest(prompt="Hello", work_dir=tmp_path)
        )
    )

    assert "GOOGLE_API_KEY" not in captured["kwargs"]["env"]


def test_chat_only_adapter_strips_provider_auth_env_without_mutating_process_env(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"gemini": "gemini-2.5-pro"},
    )
    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return FakeProcess("done\n")

    monkeypatch.setenv("GOOGLE_API_KEY", "ambient-gemini-secret")
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    original_pop = os.environ.pop

    def fail_pop(key, default=None):
        if key == "GOOGLE_API_KEY":
            raise AssertionError("process-global env mutation should not happen")
        return original_pop(key, default)

    monkeypatch.setattr(os.environ, "pop", fail_pop)

    list(
        providers["gemini"].stream(
            ProviderRequest(prompt="Hello", work_dir=tmp_path)
        )
    )

    assert "GOOGLE_API_KEY" not in captured["kwargs"]["env"]


def test_claude_adapter_isolates_ambient_home_and_config_dirs(monkeypatch, tmp_path) -> None:
    credential_store = CredentialStore(MemorySecretProvider())
    credential_store.set("claude", _credential("claude", "claude-store-secret"))
    providers = build_model_providers(
        credential_store=credential_store,
        model_by_provider={"claude": "claude-3-7-sonnet"},
    )
    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return FakeProcess("\n".join([json.dumps({"type": "result"}), ""]))

    monkeypatch.setenv("HOME", "/ambient/home")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/ambient/config")
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    list(
        providers["claude"].stream(
            ProviderRequest(prompt="Hello", work_dir=tmp_path)
        )
    )

    env = captured["kwargs"]["env"]

    assert env["HOME"] != "/ambient/home"
    assert env["XDG_CONFIG_HOME"] != "/ambient/config"


def test_chat_only_adapter_isolates_ambient_home_and_config_dirs(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"gemini": "gemini-2.5-pro"},
    )
    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return FakeProcess("done\n")

    monkeypatch.setenv("HOME", "/ambient/home")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/ambient/config")
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    list(
        providers["gemini"].stream(
            ProviderRequest(prompt="Hello", work_dir=tmp_path)
        )
    )

    env = captured["kwargs"]["env"]

    assert env["HOME"] != "/ambient/home"
    assert env["XDG_CONFIG_HOME"] != "/ambient/config"


def test_claude_adapter_launches_configured_model_id(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"claude": "claude-3-7-sonnet-20250219"},
    )
    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProcess("\n".join([json.dumps({"type": "result"}), ""]))

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    list(
        providers["claude"].stream(
            ProviderRequest(prompt="Hello", work_dir=tmp_path)
        )
    )

    assert "--model" in captured["cmd"]
    assert "claude-3-7-sonnet-20250219" in captured["cmd"]


def test_chat_only_adapter_launches_configured_model_id(monkeypatch, tmp_path) -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={"gemini": "gemini-2.5-flash"},
    )
    captured: dict[str, Any] = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProcess("done\n")

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    list(
        providers["gemini"].stream(
            ProviderRequest(prompt="Hello", work_dir=tmp_path)
        )
    )

    assert "--model" in captured["cmd"]
    assert "gemini-2.5-flash" in captured["cmd"]


def test_provider_adapters_wrap_runner_class_instances() -> None:
    providers = build_model_providers(
        credential_store=CredentialStore(MemorySecretProvider()),
        model_by_provider={
            "claude": "claude-3-7-sonnet",
            "gemini": "gemini-2.5-pro",
        },
    )

    assert cast(Any, providers["claude"])._runner.__class__.__mro__[1].__name__ == "ClaudeRunner"
    assert cast(Any, providers["gemini"])._runner.__class__.__mro__[1].__name__ == "GeminiRunner"


class TestBuildOllamaProvider:
    def test_ollama_returns_ollama_provider(self) -> None:
        from breqy.agents.providers.ollama import OllamaProvider

        store = CredentialStore(MemorySecretProvider())
        providers = build_model_providers(
            credential_store=store,
            model_by_provider={"ollama": "llama3.2"},
        )
        assert "ollama" in providers
        assert isinstance(providers["ollama"], OllamaProvider)
        assert providers["ollama"].provider_id == "ollama"
        assert providers["ollama"].model_id == "llama3.2"
        assert providers["ollama"].supports_tool_calls is True


class TestBuildCopilotProvider:
    def test_copilot_returns_copilot_provider(self) -> None:
        from breqy.agents.providers.copilot import CopilotProvider

        store = CredentialStore(MemorySecretProvider())
        providers = build_model_providers(
            credential_store=store,
            model_by_provider={"copilot": "gpt-4o"},
        )
        assert "copilot" in providers
        assert isinstance(providers["copilot"], CopilotProvider)
        assert providers["copilot"].provider_id == "copilot"
        assert providers["copilot"].model_id == "gpt-4o"
        assert providers["copilot"].supports_tool_calls is True
