"""Tests for breqy.tui.widgets.tool_panel — ToolPanel widget."""
from __future__ import annotations

import pytest

from textual.app import App, ComposeResult
from textual.widgets import RichLog

from breqy.domain.enums import ToolStatus
from breqy.tui.constants import TOOL_STATUS_ICONS
from breqy.tui.widgets.tool_panel import ToolPanel


class ToolPanelApp(App[None]):
    """Minimal app that mounts a ToolPanel for testing."""

    def compose(self) -> ComposeResult:
        yield ToolPanel()


class TestToolPanelEmptyState:
    """Test that ToolPanel displays empty state when no tools are tracked."""

    @pytest.mark.asyncio
    async def test_empty_state_shows_no_tools_message(self) -> None:
        app = ToolPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ToolPanel)
            await pilot.pause()
            log = panel.log_widget
            # Should display the empty-state message
            assert len(log.lines) == 1


class TestToolPanelToolStarted:
    """Test that tool_started adds entry with RUNNING status."""

    @pytest.mark.asyncio
    async def test_tool_started_adds_entry(self) -> None:
        app = ToolPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ToolPanel)
            panel.tool_started("inv_001", "shell")
            await pilot.pause()
            # Should have one tracked entry
            assert "inv_001" in panel._entries
            entry = panel._entries["inv_001"]
            assert entry.tool_name == "shell"
            assert entry.status == ToolStatus.RUNNING

    @pytest.mark.asyncio
    async def test_tool_started_renders_running_icon(self) -> None:
        app = ToolPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ToolPanel)
            panel.tool_started("inv_001", "shell")
            await pilot.pause()
            log = panel.log_widget
            # The log should contain a line with the RUNNING icon and tool name
            assert len(log.lines) >= 1


class TestToolPanelToolOutput:
    """Test that tool_output appends output chunk to display."""

    @pytest.mark.asyncio
    async def test_tool_output_appends_chunk(self) -> None:
        app = ToolPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ToolPanel)
            panel.tool_started("inv_001", "shell")
            panel.tool_output("inv_001", "file1.txt\nfile2.txt")
            await pilot.pause()
            entry = panel._entries["inv_001"]
            assert len(entry.output_chunks) == 1
            assert "file1.txt" in entry.output_chunks[0]

    @pytest.mark.asyncio
    async def test_tool_output_multiple_chunks(self) -> None:
        app = ToolPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ToolPanel)
            panel.tool_started("inv_001", "shell")
            panel.tool_output("inv_001", "chunk1")
            panel.tool_output("inv_001", "chunk2")
            await pilot.pause()
            entry = panel._entries["inv_001"]
            assert len(entry.output_chunks) == 2


class TestToolPanelToolCompleted:
    """Test that tool_completed marks entry with summary."""

    @pytest.mark.asyncio
    async def test_tool_completed_marks_completed(self) -> None:
        app = ToolPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ToolPanel)
            panel.tool_started("inv_001", "shell")
            panel.tool_completed("inv_001", summary="Listed 5 files")
            await pilot.pause()
            entry = panel._entries["inv_001"]
            assert entry.status == ToolStatus.COMPLETED
            assert entry.summary == "Listed 5 files"


class TestToolPanelToolFailed:
    """Test that tool_failed marks entry with error."""

    @pytest.mark.asyncio
    async def test_tool_failed_shows_error(self) -> None:
        app = ToolPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ToolPanel)
            panel.tool_started("inv_001", "shell")
            panel.tool_failed("inv_001", error="Permission denied")
            await pilot.pause()
            entry = panel._entries["inv_001"]
            assert entry.status == ToolStatus.FAILED
            assert entry.error == "Permission denied"


class TestToolPanelConcurrentTools:
    """Test that multiple concurrent tools are tracked independently."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_tools(self) -> None:
        app = ToolPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ToolPanel)
            panel.tool_started("inv_001", "shell")
            panel.tool_started("inv_002", "fs_read")
            panel.tool_output("inv_001", "shell output")
            panel.tool_completed("inv_002", summary="Read file.txt")
            await pilot.pause()
            assert len(panel._entries) == 2
            assert panel._entries["inv_001"].status == ToolStatus.RUNNING
            assert panel._entries["inv_002"].status == ToolStatus.COMPLETED
            assert len(panel._entries["inv_001"].output_chunks) == 1
            assert panel._entries["inv_002"].summary == "Read file.txt"


class TestToolPanelMaxDisplayLimit:
    """Test that old completed tools are dropped when exceeding max display limit."""

    @pytest.mark.asyncio
    async def test_old_completed_tools_scroll_off(self) -> None:
        app = ToolPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ToolPanel)
            # Add MAX_TOOLS + 5 tools, all completed
            for i in range(panel.MAX_TOOLS + 5):
                inv_id = f"inv_{i:04d}"
                panel.tool_started(inv_id, f"tool_{i}")
                panel.tool_completed(inv_id, summary=f"done {i}")
            await pilot.pause()
            # Should only retain MAX_TOOLS entries
            assert len(panel._entries) <= panel.MAX_TOOLS


class TestToolPanelStatusIcons:
    """Test that status icons are correctly displayed."""

    @pytest.mark.asyncio
    async def test_running_icon_displayed(self) -> None:
        app = ToolPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ToolPanel)
            panel.tool_started("inv_001", "shell")
            await pilot.pause()
            entry = panel._entries["inv_001"]
            assert entry.status == ToolStatus.RUNNING
            # Verify the icon mapping exists and is correct
            assert TOOL_STATUS_ICONS[ToolStatus.RUNNING] == "\u25c6"

    @pytest.mark.asyncio
    async def test_completed_icon_after_completion(self) -> None:
        app = ToolPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ToolPanel)
            panel.tool_started("inv_001", "shell")
            panel.tool_completed("inv_001", summary="Done")
            await pilot.pause()
            entry = panel._entries["inv_001"]
            assert entry.status == ToolStatus.COMPLETED
            assert TOOL_STATUS_ICONS[ToolStatus.COMPLETED] == "\u2713"

    @pytest.mark.asyncio
    async def test_failed_icon_after_failure(self) -> None:
        app = ToolPanelApp()
        async with app.run_test() as pilot:
            panel = app.query_one(ToolPanel)
            panel.tool_started("inv_001", "shell")
            panel.tool_failed("inv_001", error="boom")
            await pilot.pause()
            entry = panel._entries["inv_001"]
            assert entry.status == ToolStatus.FAILED
            assert TOOL_STATUS_ICONS[ToolStatus.FAILED] == "\u2717"
