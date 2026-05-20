# 🧹 dbt-cleaner

> **Find and drop Snowflake objects that no dbt manifest claims.**

A terminal UI for data engineers who need to keep Snowflake clean across multiple dbt projects. dbt-cleaner compares live database objects against one or more `manifest.json` files and gives you an interactive way to review and generate DROP statements — with zero risk of accidentally nuking something dbt still owns.

---

## ✨ Features

| | |
|---|---|
| 🔍 | Scans **tables, views, materialized views, dynamic tables, external tables** |
| 📦 | Supports **multiple dbt projects** targeting the same database |
| 🗄️ | Supports **multiple target databases** in a single session |
| 🔒 | **Locked schemas** — schemas with dbt objects are protected; only orphaned objects inside are listed |
| ⚙️ | **Manual mode** per schema — drop a whole schema or cherry-pick individual objects |
| 👁️ | **Implicitly Dropped** tab shows what CASCADE will remove before you commit |
| 📝 | Generates a ready-to-run `.sql` script with correct `DROP` statements per object type |
| 🔌 | Reads connections from `~/.snowflake/config.toml` with env-var override support |
| 🧩 | Extensible connector protocol — adding Postgres or Databricks = one new file |

---

## 📦 Installation

```bash
pip install dbt-cleaner
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install dbt-cleaner
```

Requires **Python 3.13+**.

---

## 🚀 Usage

### Interactive TUI

```bash
dbt-cleaner
```

Pre-fill fields from the command line:

```bash
dbt-cleaner \
  --connection prod \
  --database ANALYTICS \
  --database REPORTING \
  --manifest path/to/project_a/manifest.json \
  --manifest path/to/project_b/manifest.json
```

### CLI flags

| Flag | Short | Description |
|------|-------|-------------|
| `--connection NAME` | `-c` | Snowflake connection name from `config.toml` |
| `--database DB` | `-d` | Target database (repeatable) |
| `--manifest PATH` | `-m` | Path to `manifest.json` (repeatable) |
| `--include-schema SCHEMA` | | Only scan these schemas (repeatable) |
| `--exclude-schema SCHEMA` | | Skip these schemas (repeatable) |

---

## 🖥️ Screen flow

```
Config screen  ──►  Analysis screen  ──►  Results screen  ──►  Preview screen
  connections         scans Snowflake       review orphans        SQL + save/print
  databases           parses manifests      cycle schema state
  manifests
```

### Schema states (Results screen)

| Icon | State | Action |
|------|-------|--------|
| ○ | Not selected | No action |
| ✓ | Selected | `DROP SCHEMA … CASCADE` |
| ⚙ | Manual | Pick individual objects to drop |
| 🔒 | Locked | Schema has dbt models — protected |

Press **Enter** or **Space** to cycle state. Locked schemas cannot be changed.

---

## 🔑 Snowflake authentication

dbt-cleaner reads `~/.snowflake/config.toml`:

```toml
[connections.prod]
account = "myorg-myaccount"
user = "deploy_user"
authenticator = "externalbrowser"

[connections.dev]
account = "myorg-myaccount"
authenticator = "PROGRAMMATIC_ACCESS_TOKEN"
token = "..."
```

Environment variable overrides follow the pattern `SNOWFLAKE_CONNECTIONS_<NAME>_<PARAM>`:

```bash
export SNOWFLAKE_CONNECTIONS_DEV_TOKEN="my-pat-token"
export SNOWFLAKE_CONNECTIONS_DEV_USER="deploy_user"
```

---

## 🧠 How orphan detection works

1. Parses all supplied `manifest.json` files — `model`, `snapshot`, and `seed` nodes only (ephemeral models and sources are excluded)
2. Fetches all objects from target databases via `INFORMATION_SCHEMA`
3. Compares on `(database, schema, identifier)` — case-insensitive for unquoted identifiers
4. Classifies schemas:
   - **Orphan schema** — zero dbt coverage → candidate for `DROP SCHEMA CASCADE`
   - **Locked schema** — at least one dbt object → only un-tracked objects listed individually

---

## 📄 License

MIT
