import pytest

from breqy.tools.executor import ToolExecutor, ToolResult
from breqy.tools.registry import ToolRegistry


class EchoTool(ToolExecutor):
    name = "echo"
    description = "Echo text"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    async def execute(self, arguments: dict[str, object]) -> ToolResult:
        text = str(arguments.get("text", ""))
        return ToolResult(
            success=True,
            output={"echoed": text},
            summary=f"Echoed: {text}",
        )


class NamelessTool(ToolExecutor):
    description = "Missing stable identity"

    async def execute(self, arguments: dict[str, object]) -> ToolResult:
        return ToolResult(success=True)


def test_tool_registry_register_and_get() -> None:
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)

    assert registry.get("echo") is tool
    assert registry.get("missing") is None
    assert "echo" in registry.list_tools()


@pytest.mark.asyncio
async def test_tool_result_round_trip() -> None:
    result = await EchoTool().execute({"text": "hello"})

    assert result.success is True
    assert result.output == {"echoed": "hello"}
    assert result.error == ""


def test_registry_rejects_duplicate_names() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(EchoTool())


def test_registry_rejects_empty_tool_names() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValueError, match="empty tool name"):
        registry.register(NamelessTool())


def test_registry_to_definitions_returns_tool_definitions() -> None:
    from breqy.agents.providers.base import ToolDefinition

    registry = ToolRegistry()
    registry.register(EchoTool())

    defs = registry.to_definitions()

    assert len(defs) == 1
    assert isinstance(defs[0], ToolDefinition)
    assert defs[0].name == "echo"
    assert defs[0].description == "Echo text"
    assert defs[0].input_schema == {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }


def test_registry_to_definitions_filters_by_names() -> None:
    from breqy.agents.providers.base import ToolDefinition

    class AnotherTool(ToolExecutor):
        name = "another"
        description = "Another tool"

        async def execute(self, arguments: dict[str, object]) -> ToolResult:
            return ToolResult(success=True)

    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(AnotherTool())

    defs = registry.to_definitions(names=["echo"])

    assert len(defs) == 1
    assert defs[0].name == "echo"


def test_registry_to_definitions_empty_registry() -> None:
    registry = ToolRegistry()

    defs = registry.to_definitions()

    assert defs == []
