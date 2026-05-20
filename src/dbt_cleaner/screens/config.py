from __future__ import annotations

import re
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.validation import ValidationResult, Validator
from textual.widgets import Button, Footer, Header, Input, Label, ListItem, ListView, Select, Static

from dbt_cleaner.connectors.snowflake import SnowflakeConnector
from dbt_cleaner.models import AnalysisConfig

_DB_RE = re.compile(r"^[A-Za-z0-9_$]+$")


class _DatabaseValidator(Validator):
    def validate(self, value: str) -> ValidationResult:
        if not value.strip():
            return self.failure("Database name required")
        if not _DB_RE.match(value.strip()):
            return self.failure("Only alphanumeric, underscore, and $ allowed")
        return self.success()


class ConfigScreen(Screen):
    BINDINGS = [Binding("escape", "app.quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self._manifest_paths: list[str] = []
        self._databases: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
        with Vertical(id="main"):
            with ScrollableContainer(id="config-scroll"):
                yield Label("Snowflake Connection", classes="field-label")
                connections = SnowflakeConnector.list_available_connections()
                if connections:
                    options = [(c, c) for c in connections]
                    default = SnowflakeConnector.default_connection_name()
                    app_initial = getattr(self.app, "initial_connection", "")
                    if app_initial in connections:
                        initial = app_initial
                    elif default in connections:
                        initial = default
                    else:
                        initial = connections[0]
                    yield Select(options, value=initial, id="connection-select")
                    yield Static("", id="connection-warning")
                else:
                    yield Static(
                        "⚠ No connections found in config.toml. Enter name manually:",
                        id="connection-warning",
                        classes="warning",
                    )
                    yield Input(
                        value=getattr(self.app, "initial_connection", ""),
                        placeholder="e.g. my_snowflake_conn",
                        id="connection-input",
                    )

                yield Label("Target Databases", classes="field-label")
                yield ListView(id="database-list")
                with Horizontal(id="database-add-row"):
                    yield Input(
                        placeholder="e.g. PROD_DB",
                        id="database-input",
                        validators=[_DatabaseValidator()],
                    )
                    yield Button("Add", id="database-add-btn", variant="primary")
                yield Static("", id="database-error", classes="error")

                yield Label("dbt Manifest Files", classes="field-label")
                yield ListView(id="manifest-list")
                with Horizontal(id="manifest-add-row"):
                    yield Input(placeholder="Path to manifest.json", id="manifest-input")
                    yield Button("Add", id="manifest-add-btn", variant="primary")
                yield Static("", id="manifest-error", classes="error")

                yield Label(
                    "Include Schemas (comma-separated, leave blank for all)",
                    classes="field-label",
                )
                yield Input(
                    value=", ".join(getattr(self.app, "initial_include_schemas", [])),
                    placeholder="e.g. ANALYTICS, MARTS",
                    id="include-schemas-input",
                )

                yield Label("Exclude Schemas (comma-separated)", classes="field-label")
                yield Input(
                    value=", ".join(getattr(self.app, "initial_exclude_schemas", [])),
                    placeholder="e.g. RAW, STAGING",
                    id="exclude-schemas-input",
                )

            with Horizontal(id="config-footer"):
                yield Button("Run Analysis", id="run-btn", variant="success")

    def on_mount(self) -> None:
        for db in getattr(self.app, "initial_databases", []):
            self._add_database(db)
        for p in getattr(self.app, "initial_manifests", []):
            self._add_manifest(p)

    def _add_database(self, name: str) -> None:
        name = name.strip().upper()
        if not name or not _DB_RE.match(name):
            return
        if name in self._databases:
            return
        self._databases.append(name)
        lv = self.query_one("#database-list", ListView)
        item = ListItem(Label(name, classes="database-name"))
        item.data = name  # type: ignore[attr-defined]
        lv.append(item)

    def _add_manifest(self, path: str) -> None:
        path = path.strip()
        if not path:
            return
        if path in self._manifest_paths:
            return
        self._manifest_paths.append(path)
        lv = self.query_one("#manifest-list", ListView)
        item = ListItem(
            Label(path, classes="manifest-path"),
        )
        item.data = path  # type: ignore[attr-defined]
        lv.append(item)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "database-add-btn":
            inp = self.query_one("#database-input", Input)
            self._validate_and_add_database(inp.value)
            inp.value = ""
        elif event.button.id == "manifest-add-btn":
            inp = self.query_one("#manifest-input", Input)
            self._validate_and_add_manifest(inp.value)
            inp.value = ""
        elif event.button.id == "run-btn":
            self._run_analysis()

    def _validate_and_add_database(self, name: str) -> None:
        err = self.query_one("#database-error", Static)
        name = name.strip().upper()
        if not name:
            err.update("Database name required")
            return
        if not _DB_RE.match(name):
            err.update("Only alphanumeric, underscore, and $ allowed")
            return
        err.update("")
        self._add_database(name)

    def _validate_and_add_manifest(self, path: str) -> None:
        err = self.query_one("#manifest-error", Static)
        path = path.strip()
        if not path:
            err.update("Path cannot be empty")
            return
        if not Path(path).exists():
            err.update(f"File not found: {path}")
            return
        err.update("")
        self._add_manifest(path)

    def _get_connection_name(self) -> str:
        try:
            sel = self.query_one("#connection-select", Select)
            return str(sel.value) if sel.value else ""
        except Exception:
            pass
        try:
            inp = self.query_one("#connection-input", Input)
            return inp.value.strip()
        except Exception:
            return ""

    def _run_analysis(self) -> None:
        connection = self._get_connection_name()
        include_raw = self.query_one("#include-schemas-input", Input).value
        exclude_raw = self.query_one("#exclude-schemas-input", Input).value

        errors: list[str] = []
        if not connection:
            errors.append("Connection name required")
        if not self._databases:
            errors.append("At least one target database required")
        if not self._manifest_paths:
            errors.append("At least one manifest.json required")

        if errors:
            self.notify("\n".join(errors), severity="error", title="Validation")
            return

        def _split(raw: str) -> list[str]:
            return [s.strip() for s in raw.split(",") if s.strip()]

        config = AnalysisConfig(
            connection_name=connection,
            databases=list(self._databases),
            manifest_paths=list(self._manifest_paths),
            include_schemas=_split(include_raw),
            exclude_schemas=_split(exclude_raw),
        )
        self.app.show_analysis(config)  # type: ignore[attr-defined]
