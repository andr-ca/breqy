"""Tests for breqy.tui.screens.model_select — ModelSelectScreen."""
from __future__ import annotations

import pytest

from textual.app import App
from textual.widgets import DataTable, Static

from breqy.tui.screens.model_select import ModelOption, ModelSelectScreen


# --------------------------------------------------------------------------- #
# Test fixtures
# --------------------------------------------------------------------------- #


def _make_model(
    *,
    provider: str = "anthropic",
    model_id: str = "claude-3.5-sonnet",
    display_name: str = "Claude 3.5 Sonnet",
) -> ModelOption:
    """Factory helper for creating test ModelOption instances."""
    return ModelOption(
        provider=provider,
        model_id=model_id,
        display_name=display_name,
    )


@pytest.fixture
def sample_models() -> list[ModelOption]:
    """Return a list of models from different providers."""
    return [
        _make_model(
            provider="anthropic",
            model_id="claude-3.5-sonnet",
            display_name="Claude 3.5 Sonnet",
        ),
        _make_model(
            provider="openai",
            model_id="gpt-4",
            display_name="GPT-4",
        ),
        _make_model(
            provider="anthropic",
            model_id="claude-3-haiku",
            display_name="Claude 3 Haiku",
        ),
    ]


class ModelSelectApp(App[None]):
    """Minimal app that pushes a ModelSelectScreen for testing."""

    def __init__(
        self,
        models: list[ModelOption] | None = None,
        current_model: str = "",
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._models = models or []
        self._current_model = current_model

    def on_mount(self) -> None:
        self.push_screen(
            ModelSelectScreen(
                models=self._models,
                current_model=self._current_model,
            ),
        )


# --------------------------------------------------------------------------- #
# Mount and layout
# --------------------------------------------------------------------------- #


class TestModelSelectMounts:
    """Screen mounts and shows basic layout."""

    @pytest.mark.asyncio
    async def test_screen_mounts_with_datatable(
        self, sample_models: list[ModelOption],
    ) -> None:
        """Screen mounts and contains a DataTable widget."""
        app = ModelSelectApp(models=sample_models)
        async with app.run_test() as pilot:
            tables = app.screen.query(DataTable)
            assert len(tables) == 1

    @pytest.mark.asyncio
    async def test_header_shows_title(self) -> None:
        """Screen header shows 'Model Selection'."""
        app = ModelSelectApp()
        async with app.run_test() as pilot:
            header = app.screen.query_one("#model-select-header", Static)
            assert "Model Selection" in header.content

    @pytest.mark.asyncio
    async def test_footer_shows_key_hints(self) -> None:
        """Footer shows key hints for Enter and Escape."""
        app = ModelSelectApp()
        async with app.run_test() as pilot:
            footer = app.screen.query_one("#model-select-footer", Static)
            text = footer.content
            assert "Enter" in text
            assert "Escape" in text


# --------------------------------------------------------------------------- #
# Model display — providers and models listed
# --------------------------------------------------------------------------- #


class TestModelDisplay:
    """Available providers and models listed in the DataTable."""

    @pytest.mark.asyncio
    async def test_models_displayed_as_rows(
        self, sample_models: list[ModelOption],
    ) -> None:
        """Each model appears as a row in the DataTable."""
        app = ModelSelectApp(models=sample_models)
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            assert table.row_count == 3

    @pytest.mark.asyncio
    async def test_datatable_has_expected_columns(
        self, sample_models: list[ModelOption],
    ) -> None:
        """DataTable has columns: Selected, Provider, Model, Display Name."""
        app = ModelSelectApp(models=sample_models)
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            column_labels = [col.label.plain for col in table.columns.values()]
            assert "Provider" in column_labels
            assert "Model" in column_labels
            assert "Display Name" in column_labels


# --------------------------------------------------------------------------- #
# Current model highlighted
# --------------------------------------------------------------------------- #


class TestCurrentModelHighlighted:
    """Current model row shows a checkmark."""

    @pytest.mark.asyncio
    async def test_current_model_shows_checkmark(
        self, sample_models: list[ModelOption],
    ) -> None:
        """The row matching current_model shows '✓' in the Selected column."""
        app = ModelSelectApp(
            models=sample_models,
            current_model="gpt-4",
        )
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            # Find the row for gpt-4 (index 1) and check the Selected column
            # Row 1 is gpt-4; column 0 is Selected
            cell_value = str(table.get_cell_at((1, 0)))
            assert "✓" in cell_value

    @pytest.mark.asyncio
    async def test_non_current_models_show_space(
        self, sample_models: list[ModelOption],
    ) -> None:
        """Rows not matching current_model show space in Selected column."""
        app = ModelSelectApp(
            models=sample_models,
            current_model="gpt-4",
        )
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            # Row 0 is claude-3.5-sonnet, should NOT have ✓
            cell_value = str(table.get_cell_at((0, 0)))
            assert "✓" not in cell_value


# --------------------------------------------------------------------------- #
# Select model — Enter posts ModelSelected message
# --------------------------------------------------------------------------- #


class TestSelectModel:
    """Pressing Enter on a row posts ModelSelected and pops screen."""

    @pytest.mark.asyncio
    async def test_enter_posts_model_selected_message(
        self, sample_models: list[ModelOption],
    ) -> None:
        """Selecting a row and pressing Enter posts ModelSelected."""
        messages_received: list[ModelSelectScreen.ModelSelected] = []

        class CaptureApp(App[None]):
            def on_mount(self_app) -> None:
                self_app.push_screen(
                    ModelSelectScreen(
                        models=sample_models,
                        current_model="",
                    ),
                )

            def on_model_select_screen_model_selected(
                self_app,
                message: ModelSelectScreen.ModelSelected,
            ) -> None:
                messages_received.append(message)

        app = CaptureApp()
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            table.move_cursor(row=1)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert len(messages_received) == 1
            assert messages_received[0].provider == "openai"
            assert messages_received[0].model_id == "gpt-4"


# --------------------------------------------------------------------------- #
# Escape cancels and returns
# --------------------------------------------------------------------------- #


class TestEscapeCancels:
    """Pressing Escape pops the screen without posting ModelSelected."""

    @pytest.mark.asyncio
    async def test_escape_pops_screen_without_selection(
        self, sample_models: list[ModelOption],
    ) -> None:
        """Pressing Escape pops the screen; no ModelSelected is posted."""
        messages_received: list[ModelSelectScreen.ModelSelected] = []

        class CaptureApp(App[None]):
            def on_mount(self_app) -> None:
                self_app.push_screen(
                    ModelSelectScreen(
                        models=sample_models,
                        current_model="",
                    ),
                )

            def on_model_select_screen_model_selected(
                self_app,
                message: ModelSelectScreen.ModelSelected,
            ) -> None:
                messages_received.append(message)

        app = CaptureApp()
        async with app.run_test() as pilot:
            # Verify we're on the ModelSelectScreen
            assert isinstance(app.screen, ModelSelectScreen)
            await pilot.press("escape")
            await pilot.pause()
            # No ModelSelected should have been posted
            assert len(messages_received) == 0
            # Screen should have been popped (back to default)
            assert not isinstance(app.screen, ModelSelectScreen)


# --------------------------------------------------------------------------- #
# Empty model list handling
# --------------------------------------------------------------------------- #


class TestEmptyModelList:
    """Empty model list shows a placeholder message."""

    @pytest.mark.asyncio
    async def test_empty_models_shows_no_models_message(self) -> None:
        """When there are no models, a 'No models available' message appears."""
        app = ModelSelectApp(models=[])
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            assert table.row_count == 0
            empty_label = app.screen.query_one("#empty-models", Static)
            assert "No models available" in empty_label.content

    @pytest.mark.asyncio
    async def test_empty_label_hidden_when_models_present(
        self, sample_models: list[ModelOption],
    ) -> None:
        """The 'No models available' label is hidden when models exist."""
        app = ModelSelectApp(models=sample_models)
        async with app.run_test() as pilot:
            empty_labels = app.screen.query("#empty-models")
            if len(empty_labels) > 0:
                assert not empty_labels.first().display


# --------------------------------------------------------------------------- #
# load_models method
# --------------------------------------------------------------------------- #


class TestLoadModels:
    """load_models clears and reloads the DataTable."""

    @pytest.mark.asyncio
    async def test_load_models_replaces_rows(
        self, sample_models: list[ModelOption],
    ) -> None:
        """Calling load_models replaces existing rows."""
        app = ModelSelectApp(models=sample_models)
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            assert table.row_count == 3

            screen = app.screen
            assert isinstance(screen, ModelSelectScreen)
            new_models = [
                _make_model(
                    provider="google",
                    model_id="gemini-pro",
                    display_name="Gemini Pro",
                ),
            ]
            screen.load_models(new_models, current_model="gemini-pro")
            await pilot.pause()
            assert table.row_count == 1
            # Verify the new current model is checked
            cell_value = str(table.get_cell_at((0, 0)))
            assert "✓" in cell_value


# --------------------------------------------------------------------------- #
# Duplicate model_id across providers (DuplicateKey fix)
# --------------------------------------------------------------------------- #


class TestDuplicateModelIds:
    """Models with the same model_id must not crash — even from same provider."""

    @pytest.mark.asyncio
    async def test_duplicate_model_ids_no_crash(self) -> None:
        """Two providers offering the same model_id should not raise DuplicateKey."""
        models = [
            _make_model(provider="copilot", model_id="gpt-4", display_name="GPT 4 (Copilot)"),
            _make_model(provider="openai", model_id="gpt-4", display_name="GPT 4 (OpenAI)"),
        ]
        app = ModelSelectApp(models=models)
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_duplicate_model_ids_both_selectable(self) -> None:
        """Both rows with duplicate model_ids should be present and selectable."""
        models = [
            _make_model(provider="copilot", model_id="gpt-4", display_name="GPT 4 (Copilot)"),
            _make_model(provider="openai", model_id="gpt-4", display_name="GPT 4 (OpenAI)"),
        ]
        messages_received: list[ModelSelectScreen.ModelSelected] = []

        class CaptureApp(App[None]):
            def on_mount(self_app) -> None:
                self_app.push_screen(ModelSelectScreen(models=models, current_model=""))

            def on_model_select_screen_model_selected(
                self_app, message: ModelSelectScreen.ModelSelected
            ) -> None:
                messages_received.append(message)

        app = CaptureApp()
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            # Select second row (openai/gpt-4)
            table.move_cursor(row=1)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert len(messages_received) == 1
            assert messages_received[0].provider == "openai"
            assert messages_received[0].model_id == "gpt-4"

    @pytest.mark.asyncio
    async def test_load_models_with_duplicates_no_crash(self) -> None:
        """load_models with duplicate model_ids should not crash on reload."""
        models = [
            _make_model(provider="copilot", model_id="gpt-4", display_name="GPT 4 (Copilot)"),
            _make_model(provider="openai", model_id="gpt-4", display_name="GPT 4 (OpenAI)"),
        ]
        app = ModelSelectApp(models=[])
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ModelSelectScreen)
            screen.load_models(models, current_model="gpt-4")
            await pilot.pause()
            table = screen.query_one(DataTable)
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_exact_duplicate_same_provider_no_crash(self) -> None:
        """Same provider listing the same model_id twice should not crash."""
        models = [
            _make_model(provider="copilot", model_id="gpt-4", display_name="GPT 4"),
            _make_model(provider="copilot", model_id="gpt-4", display_name="GPT 4"),
        ]
        app = ModelSelectApp(models=models)
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_exact_duplicate_selectable(self) -> None:
        """Selecting the second of two exact-duplicate rows returns correct data."""
        models = [
            _make_model(provider="copilot", model_id="gpt-4", display_name="GPT 4 (first)"),
            _make_model(provider="copilot", model_id="gpt-4", display_name="GPT 4 (second)"),
        ]
        messages_received: list[ModelSelectScreen.ModelSelected] = []

        class CaptureApp(App[None]):
            def on_mount(self_app) -> None:
                self_app.push_screen(ModelSelectScreen(models=models, current_model=""))

            def on_model_select_screen_model_selected(
                self_app, message: ModelSelectScreen.ModelSelected
            ) -> None:
                messages_received.append(message)

        app = CaptureApp()
        async with app.run_test() as pilot:
            table = app.screen.query_one(DataTable)
            table.move_cursor(row=1)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert len(messages_received) == 1
            assert messages_received[0].provider == "copilot"
            assert messages_received[0].model_id == "gpt-4"
