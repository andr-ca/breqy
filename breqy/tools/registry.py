from __future__ import annotations

from breqy.agents.providers.base import ToolDefinition
from breqy.tools.executor import ToolExecutor


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolExecutor] = {}

    def register(self, tool: ToolExecutor) -> None:
        if not tool.name:
            raise ValueError("Cannot register tool with empty tool name")
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolExecutor | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def iter_tools(self) -> list[ToolExecutor]:
        return list(self._tools.values())

    def to_definitions(self, *, names: list[str] | None = None) -> list[ToolDefinition]:
        """Convert registered tools to ToolDefinition objects for LLM providers.

        Args:
            names: If provided, only include tools whose names are in this list.
                   If None, include all registered tools.
        """
        tools = self._tools.values()
        if names is not None:
            name_set = set(names)
            tools = [t for t in tools if t.name in name_set]
        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=dict(tool.input_schema),
            )
            for tool in tools
        ]
