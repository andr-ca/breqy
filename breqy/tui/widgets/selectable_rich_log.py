"""SelectableRichLog — RichLog subclass with working text selection.

Textual 8.x has built-in text selection support (``ALLOW_SELECT``, mouse
drag, ``copy_to_clipboard``), but ``RichLog`` does not implement the two
pieces the selection system requires:

1. ``Strip.apply_offsets(scroll_x, y)`` in ``render_line`` — tells
   Textual the position of each character for mouse hit-testing.
2. Selection highlight rendering — checking ``self.text_selection`` and
   applying the ``screen--selection`` style to the selected range.

The newer ``Log`` widget does both (see ``Log._render_line_strip``), but
it only accepts plain strings — no Rich markup.  This subclass adds both
to ``RichLog`` so that all existing Rich-markup rendering is preserved.

Additionally, ``get_selection`` is overridden to extract text from the
actual rendered lines rather than the debug ``Panel`` returned by the
inherited ``ScrollView.render()``.
"""

from __future__ import annotations

from rich.style import Style as RichStyle
from textual.app import ScreenStackError
from textual.css.query import NoMatches
from textual.selection import Selection
from textual.strip import Strip
from textual.widgets import RichLog


def _apply_selection_highlight(
    strip: Strip,
    start: int,
    end: int,
    style: RichStyle,
) -> Strip:
    """Apply *style* to characters [*start*, *end*) within *strip*.

    Uses ``Strip.divide`` to split at the selection boundaries and
    ``apply_style`` on the selected portion, then reassembles.  If the
    bounds are out of range the strip is returned unchanged.
    """
    cell_length = strip.cell_length
    if cell_length == 0 or start >= cell_length:
        return strip

    # Clamp end: -1 means "to end of line" (Selection convention)
    if end == -1 or end > cell_length:
        end = cell_length

    if start >= end:
        return strip

    # Build cut points: start, end, total length
    cuts = [c for c in (start, end, cell_length) if 0 < c <= cell_length]
    # Deduplicate while preserving order
    seen: set[int] = set()
    unique_cuts: list[int] = []
    for c in cuts:
        if c not in seen:
            seen.add(c)
            unique_cuts.append(c)

    parts = list(strip.divide(unique_cuts))

    if not parts:
        return strip

    # Determine which part index corresponds to the selected text
    # With cuts [start, end, total]:
    #   parts[0] = [0, start)   (before selection)  -- only if start > 0
    #   parts[?] = [start, end) (selection)
    #   parts[?] = [end, total) (after selection)    -- only if end < total
    selection_idx = 0 if start == 0 else 1 if len(parts) > 1 else 0

    if selection_idx < len(parts):
        parts[selection_idx] = parts[selection_idx].apply_style(style)

    return Strip.join(parts)


class SelectableRichLog(RichLog):
    """RichLog with working Textual text selection and clipboard support."""

    ALLOW_SELECT = True

    def selection_updated(self, selection: Selection | None) -> None:
        """Clear the line cache when selection changes.

        Without this override cached strips are served without the
        selection highlight, causing stale rendering when the user
        drags to change the selection or releases the mouse.
        """
        self._line_cache.clear()
        self.refresh()

    def render_line(self, y: int) -> Strip:
        """Render a line with positional offsets for text selection.

        Extends the base ``RichLog.render_line`` by calling
        ``apply_offsets`` on the resulting strip and applying the
        selection highlight style when text is selected.
        """
        scroll_x, scroll_y = self.scroll_offset
        absolute_y = scroll_y + y
        width = self.scrollable_content_region.width

        if absolute_y >= len(self.lines):
            return Strip.blank(width, self.rich_style)

        # Build the strip from the line cache (same logic as base RichLog)
        key = (absolute_y + self._start_line, scroll_x, width, self._widest_line_width)
        cached = self._line_cache.get(key)
        if cached is not None and self.text_selection is None:
            strip = cached.apply_style(self.rich_style)
            strip = strip.apply_offsets(scroll_x, y)
            return strip

        line = self.lines[absolute_y].crop_extend(
            scroll_x,
            scroll_x + width,
            self.rich_style,
        )

        # Apply selection highlighting when text is selected
        selection = self.text_selection
        if selection is not None:
            span = selection.get_span(y)
            if span is not None:
                start, end = span
                try:
                    sel_style = self.screen.get_component_rich_style(
                        "screen--selection",
                    )
                except (ScreenStackError, NoMatches):
                    sel_style = RichStyle(reverse=True)
                line = _apply_selection_highlight(line, start, end, sel_style)

        strip = line.apply_style(self.rich_style)
        strip = strip.apply_offsets(scroll_x, y)

        # Only cache when there is no active selection
        if selection is None:
            self._line_cache[key] = line

        return strip

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """Extract text under the selection from actual log content.

        The base ``ScrollView.get_selection`` calls ``self._render()``
        which returns a debug ``Panel`` — not the actual log content.
        This override reconstructs the visible text from ``self.lines``
        and uses ``Selection.extract`` to pull out the selected portion.
        """
        if not self.lines:
            return None

        # Reconstruct full text from rendered strips
        text_lines = [strip.text for strip in self.lines]
        full_text = "\n".join(text_lines)
        extracted = selection.extract(full_text)
        if not extracted:
            return None
        return extracted, "\n"
