from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, TextArea

from dbt_cleaner.models import AnalysisConfig


class _SaveModal(ModalScreen[str | None]):
    """Small modal to enter a filename for saving SQL."""

    def __init__(self, default_path: str) -> None:
        super().__init__()
        self._default = default_path

    def compose(self) -> ComposeResult:
        yield Label("Save SQL to file:", id="save-label")
        yield Input(value=self._default, id="save-input")
        with Horizontal():
            yield Button("Save", id="save-ok", variant="primary")
            yield Button("Cancel", id="save-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-ok":
            self.dismiss(self.query_one("#save-input", Input).value.strip())
        else:
            self.dismiss(None)


class PreviewScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def __init__(self, sql: str, config: AnalysisConfig) -> None:
        super().__init__()
        self._sql = sql
        self._config = config

    def compose(self) -> ComposeResult:
        line_count = self._sql.count("\n") + 1
        yield Label(
            f"Generated SQL  ({line_count} lines) — review before running",
            id="preview-title",
        )
        yield TextArea(
            self._sql,
            language="sql",
            read_only=True,
            id="sql-area",
        )
        with Horizontal(id="preview-footer"):
            yield Button("Save to file…", id="save-btn", variant="primary")
            yield Button("Print to stdout", id="print-btn")
            yield Button("Close", id="close-btn", variant="error")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self._do_save()
        elif event.button.id == "print-btn":
            # Exit the whole app with the SQL as return value; main() prints it
            self.app.exit(self._sql)
        elif event.button.id == "close-btn":
            self.dismiss()

    def _do_save(self) -> None:
        ts = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
        default = f"dbt_cleaner_{self._config.database}_{ts}.sql"

        def _handle_path(path: str | None) -> None:
            if not path:
                return
            try:
                Path(path).write_text(self._sql, encoding="utf-8")
                self.notify(f"Saved to {path}", title="Saved")
            except OSError as exc:
                self.notify(str(exc), severity="error", title="Save failed")

        self.app.push_screen(_SaveModal(default), _handle_path)
