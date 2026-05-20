# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                          # install all deps (including dev)
uv run dbt-cleaner               # launch the TUI
uv run dbt-cleaner --help        # CLI flags
uv run pytest tests/             # full test suite
uv run pytest tests/test_analyzer.py::test_no_orphans  # single test
uv run ruff check src/           # lint
uv run ruff format src/          # format
uv run mypy src/                 # type check
```

## Architecture

The app has two independent layers: **pure business logic** (no I/O, fully tested) and **TUI screens** (Textual, not unit-tested).

### Business logic layer

- `models.py` — shared dataclasses. Every other module imports from here. `SnowflakeObject.drop_sql()` returns the correct `DROP` statement for each object type.
- `manifest.py` — parses one or more `manifest.json` files. Only `model`, `snapshot`, `seed` nodes that are not `ephemeral` produce `DbtObject`s. `sources` are intentionally skipped. Identifiers are upper-cased to match Snowflake storage (quoted identifiers like `"myModel"` preserve case).
- `analyzer.py` — pure orphan detection (`analyze()` function, no I/O). Compares Snowflake objects against a known set built from dbt manifests. Classifies schemas as *orphan_schema* (zero dbt coverage → `DROP SCHEMA CASCADE`) or emits individual *orphan_objects* within mixed schemas. Objects in orphan schemas are excluded from `orphan_objects` to avoid double-counting.
- `sql_gen.py` — formats DROP statements into a `.sql` script.

### Connector layer

`connectors/base.py` defines `DatabaseConnector` as a `typing.Protocol`. Adding a new backend (Postgres, Databricks) = new file in `connectors/` implementing the Protocol, no other files change.

`connectors/snowflake.py` — synchronous, uses `snowflake-connector-python`. Reads `~/.snowflake/config.toml` via stdlib `tomllib` to enumerate available connections. Runs two queries: `INFORMATION_SCHEMA.TABLES` (tables + views) and `INFORMATION_SCHEMA.DYNAMIC_TABLES()` (separate because dynamic tables don't appear in TABLES). All identifiers are upper-cased. If TABLES returns "too much data", falls back to querying schema-by-schema.

### TUI layer

`app.py` (`DbtCleanerApp`) owns screen routing. Flow:

```
ConfigScreen → (switch_screen) → AnalysisScreen → (switch_screen) → ResultsScreen
                                                                         ↓ (push_screen)
                                                                     PreviewScreen
```

`screens/analysis.py` — runs the blocking Snowflake connector in `@work(thread=True)`; uses `call_from_thread()` to update the `ProgressBar` and status `Label`. On success calls `app.show_results()`; on error shows a notification and lets the user go back.

`screens/results.py` — two `SelectionList` widgets (one per `TabbedContent` tab): orphaned schemas and orphaned objects. Both are pre-selected. "Generate SQL" builds the DROP script and pushes `PreviewScreen`.

`screens/preview.py` — `TextArea(read_only=True, language="sql")`. "Print to stdout" calls `app.exit(sql)`; `main.py` catches the return value and `print()`s it after the TUI exits.

### Identifier normalisation

Snowflake stores unquoted identifiers in UPPER CASE. `manifest.py:_normalize_identifier()` upper-cases bare identifiers and strips surrounding double-quotes from quoted ones (preserving their case). The `analyzer.py` known-set lookup always upper-cases both sides, so comparison is case-insensitive for normal identifiers.
