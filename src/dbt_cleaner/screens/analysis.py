from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, LoadingIndicator, ProgressBar
from textual.worker import Worker, WorkerState

from dbt_cleaner.analyzer import analyze
from dbt_cleaner.connectors.snowflake import SnowflakeConnector
from dbt_cleaner.manifest import load_manifests
from dbt_cleaner.models import AnalysisConfig, AnalysisResult


class AnalysisScreen(Screen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, config: AnalysisConfig) -> None:
        super().__init__()
        self._config = config
        self._worker: Worker | None = None

    def compose(self) -> ComposeResult:
        n = len(self._config.databases)
        yield Header()
        yield Footer()
        with Vertical(id="main"):
            with Center():
                with Vertical(id="analysis-box"):
                    yield Label("Connecting to Snowflake…", id="status-label")
                    yield ProgressBar(total=2 + n + 1, show_eta=False, id="progress")
                    yield LoadingIndicator()
                    yield Button("Cancel", id="cancel-btn", variant="error")

    def on_mount(self) -> None:
        self._worker = self._run_analysis()

    @work(thread=True, exit_on_error=False)
    def _run_analysis(self) -> AnalysisResult:
        app = self.app  # capture reference; safe to access from thread

        def status(msg: str) -> None:
            app.call_from_thread(self.query_one("#status-label", Label).update, msg)

        def advance() -> None:
            app.call_from_thread(self.query_one("#progress", ProgressBar).advance, 1)

        status("Parsing dbt manifests…")
        dbt_objects = load_manifests(self._config.manifest_paths)
        advance()

        status("Connecting to Snowflake…")
        connector = SnowflakeConnector.from_connection_name(self._config.connection_name)
        advance()

        schemas = self._config.include_schemas or None
        all_sf_objects = []
        for db in self._config.databases:
            status(f"Scanning database {db}…")
            all_sf_objects.extend(connector.list_objects(db, schemas))
            advance()

        status("Analyzing orphans…")
        result = analyze(self._config, all_sf_objects, dbt_objects)
        connector.close()
        advance()

        return result

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state == WorkerState.SUCCESS:
            result: AnalysisResult = event.worker.result  # type: ignore[assignment]
            if len(result.dbt_objects) == 0:
                self.notify(
                    "No dbt objects found in any manifest. Every Snowflake object "
                    "in this database will appear as an orphan. Proceed with caution.",
                    severity="warning",
                    title="Empty manifests",
                    timeout=8,
                )
            self.app.show_results(result)  # type: ignore[attr-defined]
        elif event.state == WorkerState.ERROR:
            err = event.worker.error
            self.notify(str(err), severity="error", title="Analysis failed", timeout=0)
            self.query_one("#status-label", Label).update(f"Error: {err}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.action_cancel()

    def action_cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
        from dbt_cleaner.screens.config import ConfigScreen

        self.app.switch_screen(ConfigScreen())
