import pytest

from breqy.tools.executor import ToolExecutor, ToolResult
from breqy.tools.registry import ToolRegistry


class EchoTool(ToolExecutor):
    name = "echo"
    description = "Echo text"

    async def execute(self, arguments: dict[str, object]) -> ToolResult:
        text = str(arguments.get("text", ""))
        return ToolResult(
            success=True,
            output={"echoed": text},
            summary=f"Echoed: {text}",
        )


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
