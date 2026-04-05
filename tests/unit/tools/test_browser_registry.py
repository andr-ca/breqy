from __future__ import annotations

from breqy.tools.browser import BrowserTool
from breqy.tools.registry import ToolRegistry


def test_browser_tool_can_be_registered() -> None:
    registry = ToolRegistry()

    registry.register(BrowserTool())

    definition = registry.to_definitions(names=["browser"])[0]
    assert definition.name == "browser"
    assert definition.input_schema
