from __future__ import annotations

from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from breqy.config.loader import load_agent_config
from breqy.tools.registry import ToolRegistry


class FakeMCPProtocolSession:
    def __init__(
        self,
        *,
        tools: list[dict[str, Any]] | None = None,
        initialize_error: Exception | None = None,
        list_error: Exception | None = None,
        call_results: dict[str, Any] | None = None,
        call_error: Exception | None = None,
    ) -> None:
        self._tools = tools or []
        self._initialize_error = initialize_error
        self._list_error = list_error
        self._call_results = call_results or {}
        self._call_error = call_error
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    async def initialize(self) -> None:
        if self._initialize_error is not None:
            raise self._initialize_error

    async def list_tools(self) -> list[dict[str, Any]]:
        if self._list_error is not None:
            raise self._list_error
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        if self._call_error is not None:
            raise self._call_error
        return self._call_results[name]

    async def close(self) -> None:
        self.closed = True


class RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def warning(self, message: str, **kwargs: Any) -> None:
        self.events.append(("warning", message, kwargs))

    def exception(self, message: str, **kwargs: Any) -> None:
        self.events.append(("exception", message, kwargs))


def make_config(server_id: str):
    from breqy.config.models import MCPServerConfig

    return MCPServerConfig(
        id=server_id,
        transport="process",
        command="python",
        args=["-m", f"{server_id}_server"],
    )


def make_client(config: Any, session: FakeMCPProtocolSession):
    from breqy.tools.mcp import MCPClient

    return MCPClient(config=config, session_factory=lambda _: session)


def test_mcp_server_config_model_accepts_process_transport() -> None:
    from breqy.config.models import MCPServerConfig

    config = MCPServerConfig(
        id="memory",
        transport="process",
        command="python",
        args=["-m", "memory_server"],
        env={"MCP_ENV": "1"},
        startup_timeout_seconds=5.0,
        request_timeout_seconds=15.0,
    )

    assert config.transport == "process"
    assert config.command == "python"
    assert config.args == ["-m", "memory_server"]
    assert config.env == {"MCP_ENV": "1"}


def test_mcp_server_config_rejects_unsafe_server_id() -> None:
    from breqy.config.models import MCPServerConfig

    with pytest.raises(ValidationError):
        MCPServerConfig(
            id="memory.prod",
            transport="process",
            command="python",
        )


def test_load_agent_config_reads_mcp_servers_from_yaml(tmp_path) -> None:
    (tmp_path / "agent.yaml").write_text(
        yaml.dump(
            {
                "id": "breqy",
                "name": "Breqy",
                "provider": "copilot",
                "model": "gpt-4o",
                "mcp_servers": [
                    {
                        "id": "memory",
                        "transport": "process",
                        "command": "python",
                        "args": ["-m", "memory_server"],
                    }
                ],
            }
        )
    )
    (tmp_path / "persona.md").write_text("You are Breqy.\n")

    config = load_agent_config(str(tmp_path))

    assert len(config.mcp_servers) == 1
    assert config.mcp_servers[0].id == "memory"
    assert config.mcp_servers[0].transport == "process"


@pytest.mark.asyncio
async def test_mcp_tool_adapter_delegates_execution_to_client() -> None:
    from breqy.tools.mcp import MCPToolAdapter

    config = make_config("memory")
    session = FakeMCPProtocolSession(call_results={"search": {"content": [{"type": "text", "text": "hello"}]}})
    client = make_client(config, session)
    await client.start()
    adapter = MCPToolAdapter(
        client=client,
        server_id="memory",
        tool_name="search",
        description="Search memory",
    )

    result = await adapter.execute({"query": "hello"})

    assert session.calls == [("search", {"query": "hello"})]
    assert adapter.name == "mcp.memory.n--search"
    assert result.success is True
    assert result.output == {"content": [{"type": "text", "text": "hello"}]}


@pytest.mark.asyncio
async def test_bootstrap_registers_namespaced_tools_from_multiple_servers() -> None:
    from breqy.tools.mcp import bootstrap_mcp_tools

    registry = ToolRegistry()
    configs = [make_config("memory"), make_config("notes")]
    sessions = {
        "memory": FakeMCPProtocolSession(
            tools=[{"name": "search", "description": "Search memory"}]
        ),
        "notes": FakeMCPProtocolSession(
            tools=[
                {"name": "list", "description": "List notes"},
                {"name": "write", "description": "Write note"},
            ]
        ),
    }

    clients = await bootstrap_mcp_tools(
        registry=registry,
        server_configs=configs,
        client_factory=lambda config: make_client(config, sessions[config.id]),
    )

    assert len(clients) == 2
    assert registry.list_tools() == [
        "mcp.memory.n--search",
        "mcp.notes.n--list",
        "mcp.notes.n--write",
    ]


@pytest.mark.asyncio
async def test_bootstrap_skips_malformed_discovery_entry_and_keeps_valid_tools(monkeypatch) -> None:
    from breqy.tools import mcp

    logger = RecordingLogger()
    monkeypatch.setattr(mcp, "logger", logger)

    registry = ToolRegistry()
    config = make_config("memory")
    session = FakeMCPProtocolSession(
        tools=[
            {"description": "missing name"},
            {"name": "   ", "description": "blank name"},
            {"name": "search.logs", "description": "Search logs"},
        ]
    )

    clients = await mcp.bootstrap_mcp_tools(
        registry=registry,
        server_configs=[config],
        client_factory=lambda cfg: make_client(cfg, session),
    )

    assert len(clients) == 1
    assert registry.list_tools() == ["mcp.memory.x--7365617263682e6c6f6773"]
    assert (
        "warning",
        "Skipping malformed MCP discovery entry",
        {"server_id": "memory", "transport": "process", "entry": {"description": "missing name"}},
    ) in logger.events


@pytest.mark.asyncio
async def test_bootstrap_normalizes_safe_and_encoded_tool_names_without_collision() -> None:
    from breqy.tools.mcp import bootstrap_mcp_tools

    registry = ToolRegistry()
    config = make_config("memory")
    session = FakeMCPProtocolSession(
        tools=[
            {"name": "search.logs", "description": "Dotted name"},
            {"name": "u--7365617263682e6c6f6773", "description": "Literal encoded-looking name"},
        ]
    )

    await bootstrap_mcp_tools(
        registry=registry,
        server_configs=[config],
        client_factory=lambda cfg: make_client(cfg, session),
    )

    assert registry.list_tools() == [
        "mcp.memory.x--7365617263682e6c6f6773",
        "mcp.memory.n--u--7365617263682e6c6f6773",
    ]


@pytest.mark.asyncio
async def test_bootstrap_skips_failed_server_and_keeps_working_tools(monkeypatch) -> None:
    from breqy.tools import mcp

    logger = RecordingLogger()
    monkeypatch.setattr(mcp, "logger", logger)

    registry = ToolRegistry()
    configs = [make_config("broken"), make_config("healthy")]
    sessions = {
        "broken": FakeMCPProtocolSession(initialize_error=RuntimeError("boom")),
        "healthy": FakeMCPProtocolSession(
            tools=[{"name": "search", "description": "Search memory"}]
        ),
    }

    clients = await mcp.bootstrap_mcp_tools(
        registry=registry,
        server_configs=configs,
        client_factory=lambda config: make_client(config, sessions[config.id]),
    )

    assert len(clients) == 1
    assert registry.list_tools() == ["mcp.healthy.n--search"]
    assert ("warning", "Failed to start MCP server", {"server_id": "broken", "transport": "process", "error": "boom"}) in logger.events


@pytest.mark.asyncio
async def test_discovery_failure_is_logged_and_does_not_crash_bootstrap(monkeypatch) -> None:
    from breqy.tools import mcp

    logger = RecordingLogger()
    monkeypatch.setattr(mcp, "logger", logger)

    registry = ToolRegistry()
    configs = [make_config("broken"), make_config("healthy")]
    sessions = {
        "broken": FakeMCPProtocolSession(list_error=RuntimeError("cannot list tools")),
        "healthy": FakeMCPProtocolSession(
            tools=[{"name": "search", "description": "Search memory"}]
        ),
    }

    clients = await mcp.bootstrap_mcp_tools(
        registry=registry,
        server_configs=configs,
        client_factory=lambda config: make_client(config, sessions[config.id]),
    )

    assert len(clients) == 1
    assert sessions["broken"].closed is True
    assert registry.list_tools() == ["mcp.healthy.n--search"]
    assert (
        "warning",
        "Failed to discover MCP tools",
        {"server_id": "broken", "transport": "process", "error": "cannot list tools"},
    ) in logger.events


@pytest.mark.asyncio
async def test_invocation_transport_failure_returns_predictable_tool_failure(monkeypatch) -> None:
    from breqy.tools import mcp

    logger = RecordingLogger()
    monkeypatch.setattr(mcp, "logger", logger)

    config = make_config("memory")
    session = FakeMCPProtocolSession(call_error=RuntimeError("transport down"))
    client = make_client(config, session)
    await client.start()
    adapter = mcp.MCPToolAdapter(
        client=client,
        server_id="memory",
        tool_name="search",
        description="Search memory",
    )

    result = await adapter.execute({"query": "hello"})

    assert result.success is False
    assert result.error == "MCP invocation failed for tool 'mcp.memory.n--search'"
    assert ("exception", "MCP tool invocation failed", {"server_id": "memory", "tool_name": "search", "local_tool_name": "mcp.memory.n--search"}) in logger.events


@pytest.mark.asyncio
async def test_malformed_remote_result_is_normalized_to_failure() -> None:
    from breqy.tools.mcp import MCPToolAdapter

    config = make_config("memory")
    session = FakeMCPProtocolSession(call_results={"search": "not-a-dict"})
    client = make_client(config, session)
    await client.start()
    adapter = MCPToolAdapter(
        client=client,
        server_id="memory",
        tool_name="search",
        description="Search memory",
    )

    result = await adapter.execute({"query": "hello"})

    assert result.success is False
    assert result.error == "Malformed MCP result for tool 'mcp.memory.n--search'"


@pytest.mark.asyncio
async def test_error_remote_result_preserves_payload_and_uses_failure_summary() -> None:
    from breqy.tools.mcp import MCPToolAdapter

    config = make_config("memory")
    payload = {
        "is_error": True,
        "content": [{"type": "text", "text": "upstream failed"}],
        "retryable": True,
        "code": "E_UPSTREAM",
    }
    session = FakeMCPProtocolSession(call_results={"search": payload})
    client = make_client(config, session)
    await client.start()
    adapter = MCPToolAdapter(
        client=client,
        server_id="memory",
        tool_name="search",
        description="Search memory",
    )

    result = await adapter.execute({"query": "hello"})

    assert result.success is False
    assert result.output == payload
    assert result.error == "upstream failed"
    assert result.summary == "Remote MCP tool mcp.memory.n--search returned an error"
