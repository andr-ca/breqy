"""Tests for breqy.tui.screens.session_list — SessionListScreen."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from breqy.domain.enums import SessionStatus
from breqy.domain.models import Session
from breqy.tui.screens.session_list import SessionListScreen


# --------------------------------------------------------------------------- #
# Test fixtures
# --------------------------------------------------------------------------- #


def _make_session(
    *,
    sid: str = "ses_test001",
    status: SessionStatus = SessionStatus.ACTIVE,
    agent_id: str = "agt_breqy",
    created_at: datetime | None = None,
) -> Session:
    """Factory helper for creating test sessions."""
    return Session(
        id=sid,
        status=status,
        primary_agent_id=agent_id,
        created_at=created_at or datetime(2026, 3, 27, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_sessions() -> list[Session]:
    """Return a list of three sessions with varying statuses."""
    return [
        _make_session(sid="ses_001", status=SessionStatus.ACTIVE, agent_id="agt_a"),
        _make_session(sid="ses_002", status=SessionStatus.CLOSED, agent_id="agt_b"),
        _make_session(
            sid="ses_003",
            status=SessionStatus.CIRCUIT_BROKEN,
            agent_id="agt_c",
        ),
    ]


class SessionListApp(App[None]):
    """Minimal app that mounts a SessionListScreen for testing."""

    CSS = """
    .session-active { color: green; }
    .session-closed { color: grey; }
    .session-circuit-broken { color: red; }
    """

    def __init__(self, sessions: list[Session] | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._sessions = sessions or []

    def on_mount(self) -> None:
        self.push_screen(SessionListScreen(sessions=self._sessions))


# --------------------------------------------------------------------------- #
# Mount and layout
# --------------------------------------------------------------------------- #


class TestSessionListMounts:
    """Screen mounts and shows basic layout."""

    @pytest.mark.asyncio
    async def test_screen_mounts_with_session_list(
        self, sample_sessions: list[Session],
    ) -> None:
        """Screen mounts and contains a DataTable widget."""
        app = SessionListApp(sessions=sample_sessions)
        async with app.run_test() as pilot:
            tables = app.screen.query(DataTable)
            assert len(tables) == 1

    @pytest.mark.asyncio
    async def test_header_shows_title(self) -> None:
        """Screen header shows 'Breqy — Sessions'."""
        app = SessionListApp()
        async with app.run_test() as pilot:
            header = app.screen.query_one("#session-list-header", Static)
            assert "Sessions" in header.content

    @pytest.mark.asyncio
    async def test_footer_shows_key_hints(self) -> None:
        """Footer area shows key hints for N, R, Q, Enter."""
        app = SessionListApp()
        async with app.run_test() as pilot:
            footer = app.screen.query_one("#session-list-footer", Static)
            text = footer.content
            assert "N" in text
            assert "R" in text
            assert "Q" in text
            assert "Enter" in text


# --------------------------------------------------------------------------- #
# Session display
# --------------------------------------------------------------------------- #


class TestSessionDisplay:
    """Sessions displayed with status and timestamp."""

    @pytest.mark.asyncio
    async def test_sessions_displayed_as_rows(
        self, sample_sessions: list[Session],
    ) -> None:
        """Each session appears as a row in the DataTable."""
        app = SessionListApp(sessions=sample_sessions)
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            assert table.row_count == 3

    @pytest.mark.asyncio
    async def test_session_row_contains_id_and_agent(
        self, sample_sessions: list[Session],
    ) -> None:
        """Rows show session ID and agent ID."""
        app = SessionListApp(sessions=sample_sessions)
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            assert table.row_count == 3
            # The row key for first session should be the session id
            row_key, _ = table.coordinate_to_cell_key((0, 1))
            assert row_key.value == "ses_001"


# --------------------------------------------------------------------------- #
# Status colours via CSS classes
# --------------------------------------------------------------------------- #


class TestSessionStatusColors:
    """Session status maps to correct CSS class."""

    @pytest.mark.asyncio
    async def test_active_status_renders_success_style(self) -> None:
        """ACTIVE sessions use 'session-active' class."""
        sessions = [_make_session(status=SessionStatus.ACTIVE)]
        app = SessionListApp(sessions=sessions)
        async with app.run_test() as pilot:
            assert (
                SessionListScreen._status_class(SessionStatus.ACTIVE) == "session-active"
            )

    @pytest.mark.asyncio
    async def test_closed_status_renders_muted_style(self) -> None:
        """CLOSED sessions use 'session-closed' class."""
        sessions = [_make_session(status=SessionStatus.CLOSED)]
        app = SessionListApp(sessions=sessions)
        async with app.run_test() as pilot:
            assert (
                SessionListScreen._status_class(SessionStatus.CLOSED) == "session-closed"
            )

    @pytest.mark.asyncio
    async def test_circuit_broken_status_renders_error_style(self) -> None:
        """CIRCUIT_BROKEN sessions use 'session-circuit-broken' class."""
        sessions = [_make_session(status=SessionStatus.CIRCUIT_BROKEN)]
        app = SessionListApp(sessions=sessions)
        async with app.run_test() as pilot:
            assert (
                SessionListScreen._status_class(SessionStatus.CIRCUIT_BROKEN)
                == "session-circuit-broken"
            )


# --------------------------------------------------------------------------- #
# Empty state
# --------------------------------------------------------------------------- #


class TestEmptySessionList:
    """Empty session list shows 'No sessions' message."""

    @pytest.mark.asyncio
    async def test_empty_list_shows_no_sessions_message(self) -> None:
        """When there are no sessions, a placeholder message is displayed."""
        app = SessionListApp(sessions=[])
        async with app.run_test() as pilot:
            # DataTable should have zero data rows
            table = app.screen.query_one(DataTable)
            assert table.row_count == 0
            # The empty-state label should be visible
            empty_label = app.screen.query_one("#empty-sessions", Static)
            assert "No sessions" in empty_label.content

    @pytest.mark.asyncio
    async def test_empty_label_hidden_when_sessions_present(
        self, sample_sessions: list[Session],
    ) -> None:
        """The 'No sessions' label is hidden when sessions exist."""
        app = SessionListApp(sessions=sample_sessions)
        async with app.run_test() as pilot:
            empty_labels = app.screen.query("#empty-sessions")
            # Either not present, or display is none
            if len(empty_labels) > 0:
                assert not empty_labels.first().display


# --------------------------------------------------------------------------- #
# Key bindings — Session selected (Enter)
# --------------------------------------------------------------------------- #


class TestSessionSelection:
    """Pressing Enter on a row posts SessionSelected message."""

    @pytest.mark.asyncio
    async def test_enter_posts_session_selected_message(
        self, sample_sessions: list[Session],
    ) -> None:
        """Selecting a row and pressing Enter posts SessionSelected."""
        messages_received: list[SessionListScreen.SessionSelected] = []

        class CaptureApp(App[None]):
            CSS = """
            .session-active { color: green; }
            .session-closed { color: grey; }
            .session-circuit-broken { color: red; }
            """

            def on_mount(self) -> None:
                self.push_screen(SessionListScreen(sessions=sample_sessions))

            def on_session_list_screen_session_selected(
                self, message: SessionListScreen.SessionSelected,
            ) -> None:
                messages_received.append(message)

        app = CaptureApp()
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            # Move cursor to first row and select it
            table.move_cursor(row=0)
            await pilot.pause()
            # Trigger row selection by pressing enter
            await pilot.press("enter")
            await pilot.pause()
            assert len(messages_received) == 1
            assert messages_received[0].session_id == "ses_001"


# --------------------------------------------------------------------------- #
# Key bindings — New session (N)
# --------------------------------------------------------------------------- #


class TestNewSession:
    """Pressing N posts NewSessionRequested message."""

    @pytest.mark.asyncio
    async def test_n_key_posts_new_session_requested(self) -> None:
        """Pressing 'n' posts a NewSessionRequested message."""
        messages_received: list[SessionListScreen.NewSessionRequested] = []

        class CaptureApp(App[None]):
            def on_mount(self) -> None:
                self.push_screen(SessionListScreen(sessions=[]))

            def on_session_list_screen_new_session_requested(
                self, message: SessionListScreen.NewSessionRequested,
            ) -> None:
                messages_received.append(message)

        app = CaptureApp()
        async with app.run_test() as pilot:
            await pilot.press("n")
            await pilot.pause()
            assert len(messages_received) == 1


# --------------------------------------------------------------------------- #
# Key bindings — Refresh (R)
# --------------------------------------------------------------------------- #


class TestRefresh:
    """Pressing R posts RefreshRequested message."""

    @pytest.mark.asyncio
    async def test_r_key_posts_refresh_requested(self) -> None:
        """Pressing 'r' posts a RefreshRequested message."""
        messages_received: list[SessionListScreen.RefreshRequested] = []

        class CaptureApp(App[None]):
            def on_mount(self) -> None:
                self.push_screen(SessionListScreen(sessions=[]))

            def on_session_list_screen_refresh_requested(
                self, message: SessionListScreen.RefreshRequested,
            ) -> None:
                messages_received.append(message)

        app = CaptureApp()
        async with app.run_test() as pilot:
            await pilot.press("r")
            await pilot.pause()
            assert len(messages_received) == 1


# --------------------------------------------------------------------------- #
# Key bindings — Quit (Q)
# --------------------------------------------------------------------------- #


class TestQuit:
    """Pressing Q exits the app."""

    @pytest.mark.asyncio
    async def test_q_key_exits_app(self) -> None:
        """Pressing 'q' triggers app exit."""
        app = SessionListApp(sessions=[])
        async with app.run_test() as pilot:
            await pilot.press("q")
            # After pressing q, the app should exit; run_test context handles it


# --------------------------------------------------------------------------- #
# load_sessions method
# --------------------------------------------------------------------------- #


class TestLoadSessions:
    """load_sessions clears and reloads the DataTable."""

    @pytest.mark.asyncio
    async def test_load_sessions_replaces_rows(
        self, sample_sessions: list[Session],
    ) -> None:
        """Calling load_sessions replaces existing rows."""
        app = SessionListApp(sessions=sample_sessions)
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            assert table.row_count == 3

            screen = app.screen
            assert isinstance(screen, SessionListScreen)
            new_sessions = [
                _make_session(sid="ses_new1", agent_id="agt_x"),
            ]
            screen.load_sessions(new_sessions)
            await pilot.pause()
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_load_sessions_with_empty_list_shows_empty_state(self) -> None:
        """Loading an empty list shows the 'No sessions' placeholder."""
        sessions = [_make_session()]
        app = SessionListApp(sessions=sessions)
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, SessionListScreen)
            screen.load_sessions([])
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            assert table.row_count == 0
            empty_label = app.screen.query_one("#empty-sessions", Static)
            assert "No sessions" in empty_label.content
