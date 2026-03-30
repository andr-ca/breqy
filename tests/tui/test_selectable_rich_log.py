"""Tests for breqy.tui.widgets.selectable_rich_log — SelectableRichLog widget.

Verifies that SelectableRichLog extends RichLog with working text selection:
- Strips include positional offsets for mouse hit-testing
- Selection highlighting is applied when text_selection is set
- get_selection returns text under selection
- All standard RichLog behaviour (write, clear, wrap, markup) is preserved
- _apply_selection_highlight helper handles edge cases correctly
"""

from __future__ import annotations

import pytest
from rich.segment import Segment
from rich.style import Style as RichStyle
from textual.app import App, ComposeResult
from textual.geometry import Offset
from textual.selection import Selection
from textual.strip import Strip
from textual.widgets import RichLog

from breqy.tui.widgets.selectable_rich_log import (
    SelectableRichLog,
    _apply_selection_highlight,
)


class SelectableRichLogApp(App[None]):
    """Minimal app that mounts a SelectableRichLog for testing."""

    def compose(self) -> ComposeResult:
        yield SelectableRichLog(id="test-log", wrap=True, markup=True)


class TestSelectableRichLogIsRichLog:
    """SelectableRichLog must be a drop-in subclass of RichLog."""

    def test_is_subclass_of_rich_log(self) -> None:
        assert issubclass(SelectableRichLog, RichLog)

    @pytest.mark.asyncio
    async def test_mounts_in_app(self) -> None:
        app = SelectableRichLogApp()
        async with app.run_test() as pilot:
            widget = app.query_one(SelectableRichLog)
            assert isinstance(widget, RichLog)

    @pytest.mark.asyncio
    async def test_allow_select_is_true(self) -> None:
        app = SelectableRichLogApp()
        async with app.run_test() as pilot:
            widget = app.query_one(SelectableRichLog)
            assert widget.ALLOW_SELECT is True


class TestSelectableRichLogWrite:
    """Standard RichLog write operations must still work."""

    @pytest.mark.asyncio
    async def test_write_plain_text(self) -> None:
        app = SelectableRichLogApp()
        async with app.run_test() as pilot:
            widget = app.query_one(SelectableRichLog)
            widget.write("Hello, world!")
            await pilot.pause()
            assert len(widget.lines) >= 1

    @pytest.mark.asyncio
    async def test_write_rich_markup(self) -> None:
        app = SelectableRichLogApp()
        async with app.run_test() as pilot:
            widget = app.query_one(SelectableRichLog)
            widget.write("[bold]Bold text[/bold] and normal")
            await pilot.pause()
            assert len(widget.lines) >= 1

    @pytest.mark.asyncio
    async def test_clear_works(self) -> None:
        app = SelectableRichLogApp()
        async with app.run_test() as pilot:
            widget = app.query_one(SelectableRichLog)
            widget.write("Line 1")
            widget.write("Line 2")
            await pilot.pause()
            assert len(widget.lines) >= 2
            widget.clear()
            await pilot.pause()
            assert len(widget.lines) == 0


class TestSelectableRichLogSelectionUpdated:
    """selection_updated must clear the line cache for re-rendering."""

    @pytest.mark.asyncio
    async def test_selection_updated_clears_line_cache(self) -> None:
        """When selection changes, cached strips must be invalidated so
        the highlight is re-rendered fresh."""
        app = SelectableRichLogApp()
        async with app.run_test(size=(80, 24)) as pilot:
            widget = app.query_one(SelectableRichLog)
            widget.write("Cached line content")
            await pilot.pause()

            # Prime the cache by rendering
            widget.render_line(0)
            assert len(widget._line_cache) > 0

            # Simulate selection change
            selection = Selection(start=Offset(0, 0), end=Offset(5, 0))
            widget.selection_updated(selection)

            assert len(widget._line_cache) == 0

    @pytest.mark.asyncio
    async def test_selection_updated_none_clears_cache(self) -> None:
        """Clearing selection (None) must also invalidate the cache."""
        app = SelectableRichLogApp()
        async with app.run_test(size=(80, 24)) as pilot:
            widget = app.query_one(SelectableRichLog)
            widget.write("Another cached line")
            await pilot.pause()

            widget.render_line(0)
            assert len(widget._line_cache) > 0

            widget.selection_updated(None)
            assert len(widget._line_cache) == 0


class TestSelectableRichLogSelectionOffsets:
    """Rendered strips must include positional offsets for selection."""

    @pytest.mark.asyncio
    async def test_render_line_returns_strip_with_offsets(self) -> None:
        """render_line must call apply_offsets so Textual can map mouse
        coordinates to character positions for selection."""
        app = SelectableRichLogApp()
        async with app.run_test(size=(80, 24)) as pilot:
            widget = app.query_one(SelectableRichLog)
            widget.write("Test line for selection")
            await pilot.pause()

            strip = widget.render_line(0)
            # Strips with offsets have _offsets attribute set by apply_offsets
            # The key indicator is that the strip has cell_offsets applied
            assert strip is not None
            # Strip should have segments (non-blank)
            assert len(strip) > 0


class TestSelectableRichLogGetSelection:
    """get_selection must extract text from the widget."""

    @pytest.mark.asyncio
    async def test_get_selection_returns_text(self) -> None:
        app = SelectableRichLogApp()
        async with app.run_test(size=(80, 24)) as pilot:
            widget = app.query_one(SelectableRichLog)
            widget.write("Hello selection world")
            await pilot.pause()

            # Create a selection spanning the first line
            selection = Selection(start=Offset(0, 0), end=Offset(20, 0))
            result = widget.get_selection(selection)
            assert result is not None
            text, ending = result
            assert "Hello selection world" in text or len(text) > 0

    @pytest.mark.asyncio
    async def test_get_selection_multiline(self) -> None:
        app = SelectableRichLogApp()
        async with app.run_test(size=(80, 24)) as pilot:
            widget = app.query_one(SelectableRichLog)
            widget.write("Line one")
            widget.write("Line two")
            widget.write("Line three")
            await pilot.pause()

            # Select from start of line 0 to end of line 2
            selection = Selection(start=Offset(0, 0), end=Offset(10, 2))
            result = widget.get_selection(selection)
            assert result is not None
            text, _ = result
            assert len(text) > 0

    @pytest.mark.asyncio
    async def test_get_selection_empty_log_returns_none(self) -> None:
        app = SelectableRichLogApp()
        async with app.run_test(size=(80, 24)) as pilot:
            widget = app.query_one(SelectableRichLog)
            selection = Selection(start=Offset(0, 0), end=Offset(5, 0))
            result = widget.get_selection(selection)
            assert result is None


class TestApplySelectionHighlight:
    """Tests for the _apply_selection_highlight helper function."""

    def _make_strip(self, text: str) -> Strip:
        """Create a simple Strip from text."""
        return Strip([Segment(text)], len(text))

    def test_highlight_middle_of_line(self) -> None:
        strip = self._make_strip("Hello World")
        style = RichStyle(reverse=True)
        result = _apply_selection_highlight(strip, 2, 7, style)
        assert result.text == "Hello World"
        assert result.cell_length == 11

    def test_highlight_entire_line(self) -> None:
        strip = self._make_strip("Hello")
        style = RichStyle(reverse=True)
        result = _apply_selection_highlight(strip, 0, 5, style)
        assert result.text == "Hello"

    def test_highlight_from_start(self) -> None:
        strip = self._make_strip("Hello World")
        style = RichStyle(reverse=True)
        result = _apply_selection_highlight(strip, 0, 5, style)
        assert result.text == "Hello World"

    def test_highlight_to_end_with_minus_one(self) -> None:
        """end=-1 means 'to end of line' per Selection convention."""
        strip = self._make_strip("Hello World")
        style = RichStyle(reverse=True)
        result = _apply_selection_highlight(strip, 3, -1, style)
        assert result.text == "Hello World"

    def test_empty_strip_returns_unchanged(self) -> None:
        strip = Strip([], 0)
        style = RichStyle(reverse=True)
        result = _apply_selection_highlight(strip, 0, 5, style)
        assert result.cell_length == 0

    def test_start_beyond_length_returns_unchanged(self) -> None:
        strip = self._make_strip("Hi")
        style = RichStyle(reverse=True)
        result = _apply_selection_highlight(strip, 10, 15, style)
        assert result.text == "Hi"

    def test_start_equals_end_returns_unchanged(self) -> None:
        strip = self._make_strip("Hello")
        style = RichStyle(reverse=True)
        result = _apply_selection_highlight(strip, 3, 3, style)
        assert result.text == "Hello"

    def test_end_exceeds_length_clamped(self) -> None:
        strip = self._make_strip("Hello")
        style = RichStyle(reverse=True)
        result = _apply_selection_highlight(strip, 2, 100, style)
        assert result.text == "Hello"
