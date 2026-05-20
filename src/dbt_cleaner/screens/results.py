from __future__ import annotations

from collections import defaultdict
from enum import StrEnum

from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    SelectionList,
    TabbedContent,
    TabPane,
)
from textual.widgets.selection_list import Selection

from dbt_cleaner.models import AnalysisResult, SnowflakeObject
from dbt_cleaner.sql_gen import generate_sql


class SchemaState(StrEnum):
    NOT_SELECTED = "not_selected"  # orphan schema, not selected
    SELECTED = "selected"  # orphan schema → DROP SCHEMA CASCADE
    MANUAL = "manual"  # orphan schema → review individual objects
    LOCKED = "locked"  # has dbt objects → cannot drop wholesale


_CYCLE: dict[SchemaState, SchemaState] = {
    SchemaState.NOT_SELECTED: SchemaState.SELECTED,
    SchemaState.SELECTED: SchemaState.MANUAL,
    SchemaState.MANUAL: SchemaState.NOT_SELECTED,
}


def _icon(state: SchemaState) -> Text:
    match state:
        case SchemaState.NOT_SELECTED:
            return Text("○")
        case SchemaState.SELECTED:
            return Text("✓", style="bold green")
        case SchemaState.MANUAL:
            return Text("⚙", style="bold bright_yellow")
        case SchemaState.LOCKED:
            return Text("🔒")


class ResultsScreen(Screen):
    BINDINGS = [
        Binding("g", "generate", "Generate SQL"),
    ]

    def __init__(self, result: AnalysisResult) -> None:
        super().__init__()
        self._result = result

        # Schema state map — keyed by (database, schema) tuple
        self._states: dict[tuple[str, str], SchemaState] = {}
        for s in result.locked_schemas:
            self._states[s] = SchemaState.LOCKED
        for s in result.orphan_schemas:
            self._states[s] = SchemaState.NOT_SELECTED

        # Pre-group Snowflake objects by (database, schema) for fast lookup
        self._by_schema: dict[tuple[str, str], list[SnowflakeObject]] = defaultdict(list)
        for obj in result.snowflake_objects:
            self._by_schema[(obj.database.upper(), obj.schema.upper())].append(obj)

    # ── derived data ────────────────────────────────────────────────────────

    def _objects_for_selection(self) -> list[SnowflakeObject]:
        """Objects shown in the Orphaned Objects tab (individually selectable).

        Includes:
        - Orphaned objects from locked schemas (always present)
        - All objects from manual schemas
        """
        objs: list[SnowflakeObject] = list(self._result.orphan_objects)
        for db_schema, state in sorted(self._states.items()):
            if state == SchemaState.MANUAL:
                objs.extend(self._by_schema.get(db_schema, []))
        return sorted(set(objs), key=lambda o: (o.database, o.schema, o.name))

    def _implicit_drops(self) -> list[SnowflakeObject]:
        """Objects in SELECTED schemas — dropped implicitly by CASCADE. Read-only."""
        selected = {s for s, st in self._states.items() if st == SchemaState.SELECTED}
        return sorted(
            (o for o in self._result.snowflake_objects if (o.database.upper(), o.schema.upper()) in selected),
            key=lambda o: (o.database, o.schema, o.name),
        )

    # ── compose ─────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        r = self._result
        yield Header()
        yield Footer()
        with Vertical(id="main"):
            yield Label(
                f"Databases: [bold]{', '.join(r.config.databases)}[/bold]  |  "
                f"Orphan schemas: [bold]{len(r.orphan_schemas)}[/bold]  |  "
                f"Locked schemas: [bold]{len(r.locked_schemas)}[/bold]  |  "
                f"Orphan objects in locked: [bold]{len(r.orphan_objects)}[/bold]",
                id="results-summary",
            )
            if r.dynamic_tables_skipped:
                yield Label(
                    "⚠ Dynamic table scan incomplete (missing MONITOR privilege)",
                    classes="warning",
                )
            with TabbedContent(id="results-tabs"):
                with TabPane("Schemas", id="tab-schemas"):
                    yield Label(
                        "○ Not selected  |  [green]✓[/green] Drop schema (CASCADE)  |  "
                        "[yellow]⚙[/yellow] Manual — pick objects  |  🔒 Has dbt models (locked)\n"
                        "Press Enter or click to cycle state. Locked schemas cannot be changed.",
                        classes="tab-hint",
                    )
                    yield DataTable(
                        id="schema-table",
                        cursor_type="row",
                        zebra_stripes=True,
                    )
                with TabPane("Orphaned Objects", id="tab-objects"):
                    yield Label(
                        "Objects from locked schemas not in any manifest + all objects from manual schemas.",
                        classes="tab-hint",
                    )
                    yield SelectionList(id="object-list")
                with TabPane("Implicitly Dropped", id="tab-implicit"):
                    yield Label(
                        "These objects will be removed by DROP SCHEMA … CASCADE. Informational only.",
                        classes="tab-hint",
                    )
                    yield ListView(id="implicit-list")
            with Horizontal(id="results-footer"):
                yield Button("Generate SQL →", id="generate-btn", variant="success")

    # ── lifecycle ────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._build_schema_table()
        self._refresh_objects_tab()
        self._refresh_implicit_tab()
        self.call_after_refresh(self.query_one("#schema-table", DataTable).focus)

    def on_key(self, event: Key) -> None:
        if event.key == "space":
            focused = self.focused
            if isinstance(focused, DataTable):
                focused.action_select_cursor()
                event.stop()

    # ── schema table ─────────────────────────────────────────────────────────

    def _build_schema_table(self) -> None:
        table = self.query_one("#schema-table", DataTable)
        table.add_column("", key="icon", width=4)
        table.add_column("Database", key="database")
        table.add_column("Schema", key="schema")
        table.add_column("Objects in SF", key="count", width=14)

        for db, schema in sorted(self._states.keys()):
            count = len(self._by_schema.get((db, schema), []))
            row_key = f"{db}.{schema}"
            table.add_row(
                _icon(self._states[(db, schema)]),
                db,
                schema,
                str(count),
                key=row_key,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key_str = str(event.row_key.value)
        db, schema = row_key_str.split(".", 1)
        db_schema = (db, schema)
        current = self._states.get(db_schema)
        if current is None or current == SchemaState.LOCKED:
            return
        new_state = _CYCLE[current]
        self._states[db_schema] = new_state
        self.query_one("#schema-table", DataTable).update_cell(event.row_key, "icon", _icon(new_state))
        self._refresh_objects_tab()
        self._refresh_implicit_tab()

    # ── reactive tab refresh ─────────────────────────────────────────────────

    def _refresh_objects_tab(self) -> None:
        obj_list = self.query_one("#object-list", SelectionList)
        obj_list.clear_options()
        orphan_set = set(self._result.orphan_objects)
        for obj in self._objects_for_selection():
            source = "locked" if obj in orphan_set else "manual"
            label = escape(f"[{obj.object_type}] {obj.schema}.{obj.name} ({source})")
            obj_list.add_option(Selection(label, obj, initial_state=False))

    def _refresh_implicit_tab(self) -> None:
        impl_list = self.query_one("#implicit-list", ListView)
        impl_list.clear()
        for obj in self._implicit_drops():
            impl_list.append(ListItem(Label(f"[{obj.object_type}] {obj.fqn}")))

    # ── tab focus ────────────────────────────────────────────────────────────

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        pane_id = event.pane.id if event.pane else None
        if pane_id == "tab-schemas":
            self.call_after_refresh(self.query_one("#schema-table", DataTable).focus)
        elif pane_id == "tab-objects":
            self.call_after_refresh(self.query_one("#object-list", SelectionList).focus)
        elif pane_id == "tab-implicit":
            self.call_after_refresh(self.query_one("#implicit-list", ListView).focus)

    # ── generate SQL ─────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "generate-btn":
            self.action_generate()

    def action_generate(self) -> None:
        selected_schemas = [s for s, st in self._states.items() if st == SchemaState.SELECTED]
        selected_objects = list(self.query_one("#object-list", SelectionList).selected)
        if not selected_schemas and not selected_objects:
            self.notify("Nothing selected", severity="warning")
            return
        sql = generate_sql(self._result.config, selected_schemas, selected_objects)
        self.app.show_preview(sql, self._result.config)  # type: ignore[attr-defined]
