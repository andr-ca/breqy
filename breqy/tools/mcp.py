from __future__ import annotations

from typing import Any, Protocol

import structlog

from breqy.config.models import MCPServerConfig
from breqy.tools.executor import ToolExecutor, ToolResult
from breqy.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


class MCPTransportSession(Protocol):
    async def initialize(self) -> None: ...

    async def list_tools(self) -> list[dict[str, Any]]: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...

    async def close(self) -> None: ...


class MCPClient:
    def __init__(
        self,
        *,
        config: MCPServerConfig,
        session_factory: Any,
    ) -> None:
        self.config = config
        self._session_factory = session_factory
        self._session: MCPTransportSession | None = None

    async def start(self) -> None:
        session = self._session_factory(self.config)
        await session.initialize()
        self._session = session

    async def discover_tools(self) -> list[dict[str, Any]]:
        return await self._require_session().list_tools()

    async def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        return await self._require_session().call_tool(tool_name, arguments)

    async def close(self) -> None:
        if self._session is None:
            return
        await self._session.close()
        self._session = None

    def _require_session(self) -> MCPTransportSession:
        if self._session is None:
            raise RuntimeError(f"MCP server '{self.config.id}' is not started")
        return self._session


class MCPToolAdapter(ToolExecutor):
    def __init__(
        self,
        *,
        client: MCPClient,
        server_id: str,
        tool_name: str,
        description: str,
    ) -> None:
        self._client = client
        self._server_id = server_id
        self._tool_name = tool_name
        self.name = _namespaced_tool_name(server_id, tool_name)
        self.description = description

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            payload = await self._client.invoke_tool(self._tool_name, arguments)
        except Exception:
            logger.exception(
                "MCP tool invocation failed",
                server_id=self._server_id,
                tool_name=self._tool_name,
                local_tool_name=self.name,
            )
            return ToolResult(
                success=False,
                error=f"MCP invocation failed for tool '{self.name}'",
                summary=f"Failed to invoke remote MCP tool {self.name}",
            )

        if not isinstance(payload, dict):
            return ToolResult(
                success=False,
                error=f"Malformed MCP result for tool '{self.name}'",
                summary=f"Remote MCP tool {self.name} returned an invalid payload",
            )

        if "is_error" in payload:
            success = not bool(payload.get("is_error"))
            content = payload.get("content")
            if not isinstance(content, list):
                return ToolResult(
                    success=False,
                    error=f"Malformed MCP result for tool '{self.name}'",
                    summary=f"Remote MCP tool {self.name} returned an invalid payload",
                )
            error = "" if success else _extract_error_message(content) or f"Remote MCP tool {self.name} reported failure"
            return ToolResult(
                success=success,
                output=payload,
                error=error,
                summary=(
                    f"Executed remote MCP tool {self.name}"
                    if success
                    else f"Remote MCP tool {self.name} returned an error"
                ),
            )

        return ToolResult(
            success=True,
            output=payload,
            summary=f"Executed remote MCP tool {self.name}",
        )


async def bootstrap_mcp_tools(
    *,
    registry: ToolRegistry,
    server_configs: list[MCPServerConfig],
    client_factory: Any,
) -> list[MCPClient]:
    clients: list[MCPClient] = []

    for config in server_configs:
        client = client_factory(config)
        try:
            await client.start()
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning(
                "Failed to start MCP server",
                server_id=config.id,
                transport=config.transport,
                error=str(exc),
            )
            continue

        try:
            tools = await client.discover_tools()
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning(
                "Failed to discover MCP tools",
                server_id=config.id,
                transport=config.transport,
                error=str(exc),
            )
            await client.close()
            continue

        for tool in tools:
            remote_tool_name = _extract_remote_tool_name(tool)
            if remote_tool_name is None:
                logger.warning(
                    "Skipping malformed MCP discovery entry",
                    server_id=config.id,
                    transport=config.transport,
                    entry=tool,
                )
                continue
            registry.register(
                MCPToolAdapter(
                    client=client,
                    server_id=config.id,
                    tool_name=remote_tool_name,
                    description=str(tool.get("description", "")),
                )
            )

        clients.append(client)

    return clients


def _namespaced_tool_name(server_id: str, tool_name: str) -> str:
    return f"mcp.{server_id}.{_normalize_tool_segment(tool_name)}"


def _extract_remote_tool_name(tool: Any) -> str | None:
    if not isinstance(tool, dict):
        return None

    raw_name = tool.get("name")
    if not isinstance(raw_name, str):
        return None

    normalized = raw_name.strip()
    if not normalized:
        return None

    return normalized


def _normalize_tool_segment(value: str) -> str:
    candidate = value.strip()
    if candidate and all(character in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in candidate):
        return f"n--{candidate}"
    return f"x--{candidate.encode('utf-8').hex()}"


def _extract_error_message(content: list[Any]) -> str:
    messages: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text:
                messages.append(text)
    return "\n".join(messages)
