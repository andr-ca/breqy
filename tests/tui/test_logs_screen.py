"""Tests for breqy.tui.screens.logs — LogsScreen overlay."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog, Static

from breqy.tui.screens.logs import LogEntry, LogsScreen


# --------------------------------------------------------------------------- #
# Test app helper
# --------------------------------------------------------------------------- #


class LogsScreenApp(App[None]):
    """Minimal app that pushes a LogsScreen for testing."""

    def __init__(self, max_entries: int = 500, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._max_entries = max_entries

    def on_mount(self) -> None:
        self.push_screen(LogsScreen(max_entries=self._max_entries))


def _get_screen(app: App) -> LogsScreen:
    """Return the active LogsScreen from the app."""
    screen = app.screen
    assert isinstance(screen, LogsScreen)
    return screen


def _ts(hour: int = 12, minute: int = 0, second: int = 0) -> datetime:
    """Return a fixed timestamp for testing."""
    return datetime(2026, 3, 27, hour, minute, second, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Display: events with timestamp, source, type, summary
# --------------------------------------------------------------------------- #


class TestLogsScreenDisplay:
    """Events display with timestamp, source, event type, and summary."""

    @pytest.mark.asyncio
    async def test_displays_event_with_all_fields(self) -> None:
        """An added event shows timestamp, source, event_type, and summary."""
        app = LogsScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.add_event(
                timestamp=_ts(14, 30, 15),
                source="engine",
                event_type="session.created",
                summary="New session started",
            )
            await pilot.pause()
            log = screen.query_one("#logs-display", RichLog)
            # Should have exactly 1 event line (empty state removed)
            assert len(log.lines) == 1

    @pytest.mark.asyncio
    async def test_event_stored_as_log_entry(self) -> None:
        """add_event stores a LogEntry in the internal buffer."""
        app = LogsScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.add_event(
                timestamp=_ts(14, 30, 15),
                source="engine",
                event_type="session.created",
                summary="New session started",
            )
            assert len(screen._entries) == 1
            entry = screen._entries[0]
            assert isinstance(entry, LogEntry)
            assert entry.source == "engine"
            assert entry.event_type == "session.created"
            assert entry.summary == "New session started"


# --------------------------------------------------------------------------- #
# New events append to log
# --------------------------------------------------------------------------- #


class TestLogsScreenAppend:
    """New events append to the log display."""

    @pytest.mark.asyncio
    async def test_new_events_append_to_log(self) -> None:
        """Multiple events are displayed in order."""
        app = LogsScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.add_event(
                timestamp=_ts(14, 0, 0),
                source="engine",
                event_type="session.created",
                summary="Session one",
            )
            screen.add_event(
                timestamp=_ts(14, 1, 0),
                source="agt_breqy",
                event_type="message.sent",
                summary="Hello",
            )
            await pilot.pause()
            log = screen.query_one("#logs-display", RichLog)
            assert len(log.lines) == 2
            assert len(screen._entries) == 2


# --------------------------------------------------------------------------- #
# Filter by event type prefix
# --------------------------------------------------------------------------- #


class TestLogsScreenFilter:
    """Filtering events by event type prefix."""

    @pytest.mark.asyncio
    async def test_filter_by_event_type_prefix(self) -> None:
        """set_filter shows only events matching the prefix."""
        app = LogsScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.add_event(
                timestamp=_ts(14, 0, 0),
                source="engine",
                event_type="session.created",
                summary="Session one",
            )
            screen.add_event(
                timestamp=_ts(14, 1, 0),
                source="agt_breqy",
                event_type="message.sent",
                summary="Hello",
            )
            screen.add_event(
                timestamp=_ts(14, 2, 0),
                source="engine",
                event_type="session.closed",
                summary="Session ended",
            )
            screen.set_filter("session")
            await pilot.pause()
            log = screen.query_one("#logs-display", RichLog)
            # Only the two session.* events should be visible
            assert len(log.lines) == 2

    @pytest.mark.asyncio
    async def test_filter_input_triggers_set_filter(self) -> None:
        """Typing in the filter input calls set_filter with the value."""
        app = LogsScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.add_event(
                timestamp=_ts(14, 0, 0),
                source="engine",
                event_type="session.created",
                summary="Session one",
            )
            screen.add_event(
                timestamp=_ts(14, 1, 0),
                source="agt_breqy",
                event_type="message.sent",
                summary="Hello",
            )
            filter_input = screen.query_one("#filter-input", Input)
            filter_input.value = "message"
            await pilot.pause()
            log = screen.query_one("#logs-display", RichLog)
            assert len(log.lines) == 1


# --------------------------------------------------------------------------- #
# Clear filter shows all events
# --------------------------------------------------------------------------- #


class TestLogsScreenClearFilter:
    """Clearing the filter shows all events."""

    @pytest.mark.asyncio
    async def test_clear_filter_shows_all_events(self) -> None:
        """clear_filter removes the filter and shows all events."""
        app = LogsScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.add_event(
                timestamp=_ts(14, 0, 0),
                source="engine",
                event_type="session.created",
                summary="Session one",
            )
            screen.add_event(
                timestamp=_ts(14, 1, 0),
                source="agt_breqy",
                event_type="message.sent",
                summary="Hello",
            )
            screen.set_filter("session")
            await pilot.pause()
            log = screen.query_one("#logs-display", RichLog)
            assert len(log.lines) == 1

            screen.clear_filter()
            await pilot.pause()
            assert len(log.lines) == 2

    @pytest.mark.asyncio
    async def test_c_key_clears_filter(self) -> None:
        """Pressing 'c' clears the active filter when input not focused."""
        app = LogsScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.add_event(
                timestamp=_ts(14, 0, 0),
                source="engine",
                event_type="session.created",
                summary="Session one",
            )
            screen.add_event(
                timestamp=_ts(14, 1, 0),
                source="agt_breqy",
                event_type="message.sent",
                summary="Hello",
            )
            screen.set_filter("session")
            await pilot.pause()
            log = screen.query_one("#logs-display", RichLog)
            assert len(log.lines) == 1

            # Move focus away from input to the RichLog so 'c' triggers binding
            log.focus()
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()
            assert len(log.lines) == 2


# --------------------------------------------------------------------------- #
# Empty state
# --------------------------------------------------------------------------- #


class TestLogsScreenEmptyState:
    """Empty state shows 'No events' message."""

    @pytest.mark.asyncio
    async def test_empty_state_shows_no_events(self) -> None:
        """When no events exist, the display shows 'No events'."""
        app = LogsScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            log = screen.query_one("#logs-display", RichLog)
            await pilot.pause()
            # Should show empty state message
            assert len(log.lines) == 1


# --------------------------------------------------------------------------- #
# Escape returns to previous screen
# --------------------------------------------------------------------------- #


class TestLogsScreenEscape:
    """Escape key pops the screen."""

    @pytest.mark.asyncio
    async def test_escape_pops_screen(self) -> None:
        """Pressing Escape pops the LogsScreen overlay."""
        app = LogsScreenApp()
        async with app.run_test() as pilot:
            assert isinstance(app.screen, LogsScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, LogsScreen)


# --------------------------------------------------------------------------- #
# Max log buffer size (ring buffer)
# --------------------------------------------------------------------------- #


class TestLogsScreenRingBuffer:
    """Ring buffer respects max_entries limit."""

    @pytest.mark.asyncio
    async def test_ring_buffer_drops_oldest(self) -> None:
        """When max_entries is exceeded, oldest entries are dropped."""
        app = LogsScreenApp(max_entries=5)
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            for i in range(10):
                screen.add_event(
                    timestamp=_ts(14, 0, i),
                    source="engine",
                    event_type="session.created",
                    summary=f"Event {i}",
                )
            await pilot.pause()
            # deque maxlen=5 should keep only the last 5
            assert len(screen._entries) == 5
            # The oldest entry should be Event 5 (0-4 were dropped)
            assert screen._entries[0].summary == "Event 5"
            # The log display should show 5 lines
            log = screen.query_one("#logs-display", RichLog)
            assert len(log.lines) == 5


# ============================================================================ #
# Observability: Task 11 — Dual view (Events + Logs with Tab toggle)
# ============================================================================ #


class TestLogsScreenDualView:
    """Tests for Events/Logs dual view mode."""

    def test_logs_screen_has_view_mode(self) -> None:
        """LogsScreen should support 'events' and 'logs' view modes."""
        screen = LogsScreen()
        assert hasattr(screen, "_view_mode")
        assert screen._view_mode in ("events", "logs")

    def test_logs_screen_default_view_is_events(self) -> None:
        """Default view mode should be 'events'."""
        screen = LogsScreen()
        assert screen._view_mode == "events"

    def test_logs_screen_toggle_view(self) -> None:
        """toggle_view() should switch between events and logs."""
        screen = LogsScreen()
        assert screen._view_mode == "events"
        screen.toggle_view()
        assert screen._view_mode == "logs"
        screen.toggle_view()
        assert screen._view_mode == "events"

    def test_logs_screen_add_log_entry(self) -> None:
        """LogsScreen should accept Python log entries separate from domain events."""
        from breqy.tui.screens.logs import PythonLogEntry

        screen = LogsScreen()
        screen.add_log_entry(
            timestamp=_ts(14, 0, 0),
            level="INFO",
            logger_name="breqy.engine.server",
            message="Test log message",
            extra={"session_id": "ses_1"},
        )
        assert len(screen._log_entries) == 1
        assert isinstance(screen._log_entries[0], PythonLogEntry)

    def test_logs_screen_has_log_entries_deque(self) -> None:
        """LogsScreen should have a _log_entries deque for Python log entries."""
        import collections
        screen = LogsScreen()
        assert hasattr(screen, "_log_entries")
        assert isinstance(screen._log_entries, collections.deque)

    @pytest.mark.asyncio
    async def test_logs_view_renders_log_entries(self) -> None:
        """When in 'logs' mode, display should render Python log entries."""
        app = LogsScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.add_log_entry(
                timestamp=_ts(14, 0, 0),
                level="INFO",
                logger_name="breqy.engine.server",
                message="Server started",
            )
            screen.toggle_view()
            await pilot.pause()
            log = screen.query_one("#logs-display", RichLog)
            assert len(log.lines) == 1

    @pytest.mark.asyncio
    async def test_events_view_does_not_show_log_entries(self) -> None:
        """In 'events' mode, Python log entries should not appear."""
        app = LogsScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            screen.add_log_entry(
                timestamp=_ts(14, 0, 0),
                level="INFO",
                logger_name="breqy.engine.server",
                message="Server started",
            )
            # Default mode is events
            assert screen._view_mode == "events"
            await pilot.pause()
            log = screen.query_one("#logs-display", RichLog)
            # Should only have the empty state ("No events"), not the log entry
            assert len(log.lines) == 1  # "No events" message


# ============================================================================ #
# Observability: Task 12 — Filter matches source (agent_id) and event_type
# ============================================================================ #


class TestLogsScreenFilterEnhanced:
    """Filter should match source field in addition to event_type."""

    def test_filter_matches_source(self) -> None:
        """Filter should match against source field (which contains agent_id)."""
        screen = LogsScreen()
        screen._entries.append(LogEntry(
            timestamp=_ts(14, 0, 0), source="breqy",
            event_type="message_sent", summary="hello",
        ))
        screen._entries.append(LogEntry(
            timestamp=_ts(14, 1, 0), source="engine",
            event_type="session_created", summary="new session",
        ))
        screen.set_filter("breqy")
        visible = screen._get_visible_entries()
        assert len(visible) == 1
        assert visible[0].source == "breqy"

    def test_filter_still_matches_event_type(self) -> None:
        """Filter should still match event_type prefix as before."""
        screen = LogsScreen()
        screen._entries.append(LogEntry(
            timestamp=_ts(14, 0, 0), source="engine",
            event_type="session.created", summary="one",
        ))
        screen._entries.append(LogEntry(
            timestamp=_ts(14, 1, 0), source="engine",
            event_type="message.sent", summary="two",
        ))
        screen.set_filter("session")
        visible = screen._get_visible_entries()
        assert len(visible) == 1
        assert visible[0].event_type == "session.created"

    def test_filter_is_case_insensitive(self) -> None:
        """Filter matching should be case-insensitive."""
        screen = LogsScreen()
        screen._entries.append(LogEntry(
            timestamp=_ts(14, 0, 0), source="Breqy",
            event_type="MESSAGE_SENT", summary="hello",
        ))
        screen.set_filter("breqy")
        visible = screen._get_visible_entries()
        assert len(visible) == 1
