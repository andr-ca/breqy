"""ModelSelectScreen — overlay screen for choosing an AI model/provider.

The screen presents a ``DataTable`` listing available models grouped by
provider.  The user can navigate the table, press **Enter** to confirm a
selection (which posts ``ModelSelectScreen.ModelSelected``), or press
**Escape** to cancel and return to the previous screen.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import Screen
from textual.widgets import DataTable, Static


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclass
class ModelOption:
    """A selectable model entry for the model-select screen."""

    provider: str       # e.g., "anthropic", "openai"
    model_id: str       # e.g., "claude-3.5-sonnet", "gpt-4"
    display_name: str   # e.g., "Claude 3.5 Sonnet"


# --------------------------------------------------------------------------- #
# ModelSelectScreen
# --------------------------------------------------------------------------- #


class ModelSelectScreen(Screen):
    """Overlay screen for selecting an AI model/provider."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    # ------------------------------------------------------------------ #
    # Messages
    # ------------------------------------------------------------------ #

    class ModelSelected(Message):
        """Posted when the user confirms a model selection."""

        def __init__(self, provider: str, model_id: str) -> None:
            super().__init__()
            self.provider = provider
            self.model_id = model_id

    # ------------------------------------------------------------------ #
    # Init
    # ------------------------------------------------------------------ #

    def __init__(
        self,
        models: list[ModelOption] | None = None,
        current_model: str = "",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._models: list[ModelOption] = models if models is not None else []
        self._current_model: str = current_model

    # ------------------------------------------------------------------ #
    # Compose
    # ------------------------------------------------------------------ #

    def compose(self) -> ComposeResult:
        yield Static("Model Selection", id="model-select-header")
        yield DataTable(id="model-table")
        yield Static(
            "[dim]No models available[/dim]",
            id="empty-models",
        )
        yield Static(
            "[b]Enter[/b] Select  [b]Escape[/b] Cancel",
            id="model-select-footer",
        )

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def on_mount(self) -> None:
        """Configure the DataTable columns and load initial data."""
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("Selected", "Provider", "Model", "Display Name")
        self.load_models(self._models, self._current_model)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def load_models(
        self,
        models: list[ModelOption],
        current_model: str = "",
    ) -> None:
        """Clear and reload the DataTable with the given models."""
        self._models = list(models)
        self._current_model = current_model

        table = self.query_one(DataTable)
        table.clear()

        empty_label = self.query_one("#empty-models", Static)

        if not models:
            empty_label.display = True
            return

        empty_label.display = False
        for idx, model in enumerate(models):
            selected = "✓" if model.model_id == current_model else " "
            table.add_row(
                selected,
                model.provider,
                model.model_id,
                model.display_name,
                key=str(idx),
            )

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #

    def action_cancel(self) -> None:
        """Pop screen without posting a selection message."""
        self.app.pop_screen()

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        """When a row is selected, post ModelSelected and pop screen."""
        if event.row_key.value is not None:
            idx = int(event.row_key.value)
            if 0 <= idx < len(self._models):
                model = self._models[idx]
                self.post_message(
                    self.ModelSelected(provider=model.provider, model_id=model.model_id),
                )
                self.app.pop_screen()
