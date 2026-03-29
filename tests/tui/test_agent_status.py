"""Tests for breqy.tui.widgets.agent_status — AgentStatusBar widget."""
from __future__ import annotations

import pytest

from textual.app import App, ComposeResult
from textual.widgets import Static

from breqy.tui.constants import AGENT_CONNECTED_ICON, AGENT_DISCONNECTED_ICON
from breqy.tui.widgets.agent_status import AgentStatusBar


class AgentStatusApp(App[None]):
    """Minimal app that mounts an AgentStatusBar for testing."""

    def compose(self) -> ComposeResult:
        yield AgentStatusBar()


class TestAgentStatusBarCompose:
    """Test that AgentStatusBar mounts a Static widget."""

    @pytest.mark.asyncio
    async def test_mounts_static_widget(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            statics = app.query(Static)
            assert len(statics) == 1

    @pytest.mark.asyncio
    async def test_status_widget_property(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            status = bar.status_widget
            assert isinstance(status, Static)


class TestAgentStatusBarEmptyState:
    """Test empty state shows 'No agents' placeholder."""

    @pytest.mark.asyncio
    async def test_empty_state_shows_no_agents(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            await pilot.pause()
            rendered = bar.status_widget.content
            assert "No agents" in str(rendered)


class TestAgentStatusBarConnected:
    """Test connected agent shows filled circle icon."""

    @pytest.mark.asyncio
    async def test_connected_agent_shows_filled_icon(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("agt_breqy", connected=True)
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            assert AGENT_CONNECTED_ICON in rendered
            assert "breqy" in rendered


class TestAgentStatusBarDisconnected:
    """Test disconnected agent shows hollow circle icon."""

    @pytest.mark.asyncio
    async def test_disconnected_agent_shows_hollow_icon(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("agt_coder", connected=False)
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            assert AGENT_DISCONNECTED_ICON in rendered
            assert "coder" in rendered


class TestAgentStatusBarMultipleAgents:
    """Test multiple agents are displayed separated by pipe."""

    @pytest.mark.asyncio
    async def test_multiple_agents_displayed(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("agt_breqy", connected=True)
            bar.update_agent("agt_coder", connected=False)
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            assert AGENT_CONNECTED_ICON in rendered
            assert AGENT_DISCONNECTED_ICON in rendered
            assert "breqy" in rendered
            assert "coder" in rendered
            assert " | " in rendered

    @pytest.mark.asyncio
    async def test_agents_in_insertion_order(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("agt_alpha", connected=True)
            bar.update_agent("agt_beta", connected=True)
            bar.update_agent("agt_gamma", connected=False)
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            alpha_pos = rendered.find("alpha")
            beta_pos = rendered.find("beta")
            gamma_pos = rendered.find("gamma")
            assert alpha_pos < beta_pos < gamma_pos


class TestAgentStatusBarNameFormatting:
    """Test agent name formatting strips agt_ prefix."""

    @pytest.mark.asyncio
    async def test_strips_agt_prefix(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("agt_breqy", connected=True)
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            assert "breqy" in rendered
            assert "agt_" not in rendered

    @pytest.mark.asyncio
    async def test_no_prefix_agent_name_unchanged(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("planner", connected=True)
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            assert "planner" in rendered

    @pytest.mark.asyncio
    async def test_agt_prefix_only_stripped_at_start(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("my_agt_helper", connected=True)
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            # Should not strip "agt_" from middle of name
            assert "my_agt_helper" in rendered


class TestAgentStatusBarRemoveAgent:
    """Test removing an agent updates the display."""

    @pytest.mark.asyncio
    async def test_remove_agent(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("agt_breqy", connected=True)
            bar.update_agent("agt_coder", connected=True)
            await pilot.pause()
            assert len(bar._agents) == 2

            bar.remove_agent("agt_breqy")
            await pilot.pause()
            assert len(bar._agents) == 1
            rendered = str(bar.status_widget.content)
            assert "breqy" not in rendered
            assert "coder" in rendered

    @pytest.mark.asyncio
    async def test_remove_nonexistent_agent_noop(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            # Should not raise
            bar.remove_agent("agt_nonexistent")
            await pilot.pause()


class TestAgentStatusBarClear:
    """Test clearing all agents returns to empty state."""

    @pytest.mark.asyncio
    async def test_clear_agents_returns_to_empty_state(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("agt_breqy", connected=True)
            bar.update_agent("agt_coder", connected=False)
            await pilot.pause()
            assert len(bar._agents) == 2

            bar.clear_agents()
            await pilot.pause()
            assert len(bar._agents) == 0
            rendered = str(bar.status_widget.content)
            assert "No agents" in rendered


class TestAgentStatusBarStatusTransition:
    """Test that updating an existing agent's status re-renders correctly."""

    @pytest.mark.asyncio
    async def test_connected_to_disconnected(self) -> None:
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("agt_breqy", connected=True)
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            assert AGENT_CONNECTED_ICON in rendered

            bar.update_agent("agt_breqy", connected=False)
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            assert AGENT_DISCONNECTED_ICON in rendered
            # Should not duplicate the agent
            assert rendered.count("breqy") == 1


# --------------------------------------------------------------------------- #
# Phase 5 (M2): Model info display
# --------------------------------------------------------------------------- #


class TestAgentStatusBarModelInfo:
    """Test model info display alongside agent status."""

    @pytest.mark.asyncio
    async def test_update_model_info_displays_provider_and_model(self) -> None:
        """After update_model_info, status shows provider / model in cyan."""
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("agt_breqy", connected=True)
            bar.update_model_info("copilot", "gpt-4o")
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            assert "copilot" in rendered
            assert "gpt-4o" in rendered

    @pytest.mark.asyncio
    async def test_model_info_not_shown_without_update(self) -> None:
        """Model info is not shown if update_model_info was never called."""
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("agt_breqy", connected=True)
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            assert "copilot" not in rendered
            assert "gpt-4o" not in rendered

    @pytest.mark.asyncio
    async def test_clear_model_info_removes_display(self) -> None:
        """After clear_model_info, the model info is no longer shown."""
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("agt_breqy", connected=True)
            bar.update_model_info("copilot", "gpt-4o")
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            assert "copilot" in rendered

            bar.clear_model_info()
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            assert "copilot" not in rendered
            assert "gpt-4o" not in rendered

    @pytest.mark.asyncio
    async def test_null_provider_shows_warning_style(self) -> None:
        """When provider is 'null', display uses dim/warning style."""
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_agent("agt_breqy", connected=True)
            bar.update_model_info("null", "null")
            await pilot.pause()
            rendered = str(bar.status_widget.content)
            # Should display in dim style (not cyan) for null provider
            assert "null" in rendered
            assert "[dim]" in rendered or "dim" in rendered

    @pytest.mark.asyncio
    async def test_model_info_state_stored(self) -> None:
        """update_model_info stores the info as a tuple in _model_info."""
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_model_info("copilot", "gpt-4o")
            assert bar._model_info == ("copilot", "gpt-4o")

    @pytest.mark.asyncio
    async def test_clear_model_info_resets_state(self) -> None:
        """clear_model_info sets _model_info back to None."""
        app = AgentStatusApp()
        async with app.run_test() as pilot:
            bar = app.query_one(AgentStatusBar)
            bar.update_model_info("copilot", "gpt-4o")
            bar.clear_model_info()
            assert bar._model_info is None
