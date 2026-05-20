from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from dbt_cleaner.models import AnalysisConfig, AnalysisResult


class DbtCleanerApp(App[str | None]):
    """dbt-cleaner: find and remove orphaned Snowflake objects."""

    TITLE = "dbt-cleaner"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+d", "toggle_dark", "Dark mode"),
    ]

    def __init__(
        self,
        connection_name: str | None = None,
        databases: list[str] | None = None,
        manifest_paths: list[str] | None = None,
        include_schemas: list[str] | None = None,
        exclude_schemas: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.initial_connection = connection_name or ""
        self.initial_databases: list[str] = databases or []
        self.initial_manifests: list[str] = manifest_paths or []
        self.initial_include_schemas: list[str] = include_schemas or []
        self.initial_exclude_schemas: list[str] = exclude_schemas or []

    def on_mount(self) -> None:
        from dbt_cleaner.screens.config import ConfigScreen

        self.push_screen(ConfigScreen())

    def show_analysis(self, config: AnalysisConfig) -> None:
        from dbt_cleaner.screens.analysis import AnalysisScreen

        self.switch_screen(AnalysisScreen(config))

    def show_results(self, result: AnalysisResult) -> None:
        from dbt_cleaner.screens.results import ResultsScreen

        self.switch_screen(ResultsScreen(result))

    def show_preview(self, sql: str, config: AnalysisConfig) -> None:
        from dbt_cleaner.screens.preview import PreviewScreen

        self.push_screen(PreviewScreen(sql, config))
