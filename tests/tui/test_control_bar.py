"""Tests for breqy.tui.widgets.control_bar — ControlBar widget."""
from __future__ import annotations

import pytest

from textual.app import App, ComposeResult
from textual.widgets import Button, Input

from breqy.domain.enums import EventType
from breqy.tui.widgets.control_bar import ControlBar


class ControlBarApp(App[None]):
    """Minimal app that mounts a ControlBar for testing."""

    def compose(self) -> ComposeResult:
        yield ControlBar()


class TestControlBarCompose:
    """Test that ControlBar mounts expected child widgets."""

    @pytest.mark.asyncio
    async def test_mounts_four_buttons(self) -> None:
        app = ControlBarApp()
        async with app.run_test() as pilot:
            buttons = app.query(Button)
            assert len(buttons) == 4

    @pytest.mark.asyncio
    async def test_mounts_direction_input(self) -> None:
        app = ControlBarApp()
        async with app.run_test() as pilot:
            inp = app.query_one("#direction-input", Input)
            assert inp is not None

    @pytest.mark.asyncio
    async def test_direction_input_hidden_by_default(self) -> None:
        app = ControlBarApp()
        async with app.run_test() as pilot:
            inp = app.query_one("#direction-input", Input)
            assert not inp.display


class TestControlBarStopButton:
    """Test that the Stop button sends ControlAction with CONTROL_STOP."""

    @pytest.mark.asyncio
    async def test_stop_button_sends_control_stop(self) -> None:
        actions: list[ControlBar.ControlAction] = []

        class CapturingApp(ControlBarApp):
            def on_control_bar_control_action(self, event: ControlBar.ControlAction) -> None:
                actions.append(event)

        app = CapturingApp()
        async with app.run_test() as pilot:
            bar = app.query_one(ControlBar)
            bar.set_active(True)
            await pilot.pause()
            stop_btn = app.query_one("#btn-stop", Button)
            stop_btn.press()
            await pilot.pause()
            assert len(actions) == 1
            assert actions[0].event_type == EventType.CONTROL_STOP
            assert actions[0].new_direction == ""


class TestControlBarStopAndSteerButton:
    """Test that Stop+Steer button shows direction input and sends event."""

    @pytest.mark.asyncio
    async def test_stop_and_steer_button_shows_direction_input(self) -> None:
        app = ControlBarApp()
        async with app.run_test() as pilot:
            bar = app.query_one(ControlBar)
            bar.set_active(True)
            await pilot.pause()
            btn = app.query_one("#btn-stop-and-steer", Button)
            btn.press()
            await pilot.pause()
            inp = app.query_one("#direction-input", Input)
            assert inp.display

    @pytest.mark.asyncio
    async def test_stop_and_steer_sends_event_on_direction_submit(self) -> None:
        actions: list[ControlBar.ControlAction] = []

        class CapturingApp(ControlBarApp):
            def on_control_bar_control_action(self, event: ControlBar.ControlAction) -> None:
                actions.append(event)

        app = CapturingApp()
        async with app.run_test() as pilot:
            bar = app.query_one(ControlBar)
            bar.set_active(True)
            await pilot.pause()
            btn = app.query_one("#btn-stop-and-steer", Button)
            btn.press()
            await pilot.pause()
            inp = app.query_one("#direction-input", Input)
            inp.value = "Focus on tests instead"
            await inp.action_submit()
            await pilot.pause()
            assert len(actions) == 1
            assert actions[0].event_type == EventType.CONTROL_STOP_AND_STEER
            assert actions[0].new_direction == "Focus on tests instead"


class TestControlBarSteerButton:
    """Test that Steer button shows direction input and sends event."""

    @pytest.mark.asyncio
    async def test_steer_button_shows_direction_input(self) -> None:
        app = ControlBarApp()
        async with app.run_test() as pilot:
            bar = app.query_one(ControlBar)
            bar.set_active(True)
            await pilot.pause()
            btn = app.query_one("#btn-steer", Button)
            btn.press()
            await pilot.pause()
            inp = app.query_one("#direction-input", Input)
            assert inp.display

    @pytest.mark.asyncio
    async def test_steer_sends_event_on_direction_submit(self) -> None:
        actions: list[ControlBar.ControlAction] = []

        class CapturingApp(ControlBarApp):
            def on_control_bar_control_action(self, event: ControlBar.ControlAction) -> None:
                actions.append(event)

        app = CapturingApp()
        async with app.run_test() as pilot:
            bar = app.query_one(ControlBar)
            bar.set_active(True)
            await pilot.pause()
            btn = app.query_one("#btn-steer", Button)
            btn.press()
            await pilot.pause()
            inp = app.query_one("#direction-input", Input)
            inp.value = "Try a different approach"
            await inp.action_submit()
            await pilot.pause()
            assert len(actions) == 1
            assert actions[0].event_type == EventType.CONTROL_STEER
            assert actions[0].new_direction == "Try a different approach"


class TestControlBarCircuitBreak:
    """Test that Circuit Break button sends CONTROL_CIRCUIT_BREAK."""

    @pytest.mark.asyncio
    async def test_circuit_break_sends_event(self) -> None:
        actions: list[ControlBar.ControlAction] = []

        class CapturingApp(ControlBarApp):
            def on_control_bar_control_action(self, event: ControlBar.ControlAction) -> None:
                actions.append(event)

        app = CapturingApp()
        async with app.run_test() as pilot:
            btn = app.query_one("#btn-circuit-break", Button)
            btn.press()
            await pilot.pause()
            assert len(actions) == 1
            assert actions[0].event_type == EventType.CONTROL_CIRCUIT_BREAK
            assert actions[0].new_direction == ""


class TestControlBarDisabledState:
    """Test that buttons are disabled when no active session."""

    @pytest.mark.asyncio
    async def test_buttons_disabled_by_default(self) -> None:
        app = ControlBarApp()
        async with app.run_test() as pilot:
            stop = app.query_one("#btn-stop", Button)
            steer = app.query_one("#btn-steer", Button)
            stop_steer = app.query_one("#btn-stop-and-steer", Button)
            assert stop.disabled
            assert steer.disabled
            assert stop_steer.disabled

    @pytest.mark.asyncio
    async def test_disabled_stop_button_does_not_send_event(self) -> None:
        actions: list[ControlBar.ControlAction] = []

        class CapturingApp(ControlBarApp):
            def on_control_bar_control_action(self, event: ControlBar.ControlAction) -> None:
                actions.append(event)

        app = CapturingApp()
        async with app.run_test() as pilot:
            stop = app.query_one("#btn-stop", Button)
            stop.press()
            await pilot.pause()
            assert len(actions) == 0


class TestControlBarEnabledState:
    """Test that buttons are enabled when session is active."""

    @pytest.mark.asyncio
    async def test_set_active_enables_buttons(self) -> None:
        app = ControlBarApp()
        async with app.run_test() as pilot:
            bar = app.query_one(ControlBar)
            bar.set_active(True)
            await pilot.pause()
            stop = app.query_one("#btn-stop", Button)
            steer = app.query_one("#btn-steer", Button)
            stop_steer = app.query_one("#btn-stop-and-steer", Button)
            assert not stop.disabled
            assert not steer.disabled
            assert not stop_steer.disabled

    @pytest.mark.asyncio
    async def test_set_active_false_disables_buttons(self) -> None:
        app = ControlBarApp()
        async with app.run_test() as pilot:
            bar = app.query_one(ControlBar)
            bar.set_active(True)
            await pilot.pause()
            bar.set_active(False)
            await pilot.pause()
            stop = app.query_one("#btn-stop", Button)
            steer = app.query_one("#btn-steer", Button)
            stop_steer = app.query_one("#btn-stop-and-steer", Button)
            assert stop.disabled
            assert steer.disabled
            assert stop_steer.disabled


class TestControlBarCircuitBreakAlwaysEnabled:
    """Test that Circuit Break is always enabled regardless of session state."""

    @pytest.mark.asyncio
    async def test_circuit_break_enabled_when_inactive(self) -> None:
        app = ControlBarApp()
        async with app.run_test() as pilot:
            cb = app.query_one("#btn-circuit-break", Button)
            assert not cb.disabled

    @pytest.mark.asyncio
    async def test_circuit_break_stays_enabled_after_set_active_false(self) -> None:
        app = ControlBarApp()
        async with app.run_test() as pilot:
            bar = app.query_one(ControlBar)
            bar.set_active(True)
            await pilot.pause()
            bar.set_active(False)
            await pilot.pause()
            cb = app.query_one("#btn-circuit-break", Button)
            assert not cb.disabled


class TestControlBarDirectionInputBehavior:
    """Test direction input overlay behavior."""

    @pytest.mark.asyncio
    async def test_direction_input_hidden_after_submit(self) -> None:
        app = ControlBarApp()
        async with app.run_test() as pilot:
            bar = app.query_one(ControlBar)
            bar.set_active(True)
            await pilot.pause()
            btn = app.query_one("#btn-steer", Button)
            btn.press()
            await pilot.pause()
            inp = app.query_one("#direction-input", Input)
            inp.value = "new direction"
            await inp.action_submit()
            await pilot.pause()
            assert not inp.display

    @pytest.mark.asyncio
    async def test_direction_input_cleared_after_submit(self) -> None:
        app = ControlBarApp()
        async with app.run_test() as pilot:
            bar = app.query_one(ControlBar)
            bar.set_active(True)
            await pilot.pause()
            btn = app.query_one("#btn-steer", Button)
            btn.press()
            await pilot.pause()
            inp = app.query_one("#direction-input", Input)
            inp.value = "new direction"
            await inp.action_submit()
            await pilot.pause()
            assert inp.value == ""
