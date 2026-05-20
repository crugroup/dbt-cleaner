from __future__ import annotations

import os
import platform
import re
import tomllib
from pathlib import Path

import snowflake.connector
from snowflake.connector import SnowflakeConnection
from snowflake.connector.errors import ProgrammingError

from dbt_cleaner.models import SnowflakeObject, SnowflakeObjectType

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_$]+$")


def _safe_identifier(value: str) -> str:
    """Validate that an identifier is safe to interpolate into SQL (no injection)."""
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(f"Unsafe identifier: {value!r}")
    return value.upper()


def _resolve_config_toml() -> Path | None:
    snowflake_home = os.environ.get("SNOWFLAKE_HOME")
    if snowflake_home:
        return Path(snowflake_home) / "config.toml"
    candidate = Path.home() / ".snowflake" / "config.toml"
    if candidate.exists():
        return candidate
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "snowflake" / "config.toml"
    if system == "Windows":
        appdata = os.environ.get("USERPROFILE", str(Path.home()))
        return Path(appdata) / "AppData" / "Local" / "snowflake" / "config.toml"
    return Path.home() / ".config" / "snowflake" / "config.toml"


def _load_connection_params(connection_name: str) -> dict:
    """Read connection params from config.toml [connections.<name>] and apply env var overrides.

    Env var format: SNOWFLAKE_CONNECTIONS_<NAME>_<PARAM>
    e.g. SNOWFLAKE_CONNECTIONS_DEV_USER, SNOWFLAKE_CONNECTIONS_DEV_TOKEN
    """
    toml_path = _resolve_config_toml()
    params: dict = {}

    if toml_path and toml_path.exists():
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
        connections = data.get("connections", {})
        if connection_name not in connections:
            raise ValueError(
                f"Connection '{connection_name}' not found in {toml_path}. "
                f"Available: {', '.join(connections.keys()) or 'none'}"
            )
        params = dict(connections[connection_name])

    # Apply env var overrides: SNOWFLAKE_CONNECTIONS_<NAME>_<PARAM> -> param
    prefix = f"SNOWFLAKE_CONNECTIONS_{connection_name.upper()}_"
    for key, val in os.environ.items():
        if key.upper().startswith(prefix):
            param_name = key[len(prefix) :].lower()
            params[param_name] = val

    if not params:
        raise ValueError(
            f"No config found for connection '{connection_name}'. "
            f"Check {toml_path} or set SNOWFLAKE_CONNECTIONS_{connection_name.upper()}_* env vars."
        )

    return params


class SnowflakeConnector:
    """Snowflake implementation of DatabaseConnector.

    Uses synchronous snowflake-connector-python. Run in a thread worker
    (Textual @work(thread=True)) to avoid blocking the event loop.
    """

    def __init__(self, connection: SnowflakeConnection) -> None:
        self._conn = connection

    @classmethod
    def from_connection_name(cls, connection_name: str) -> SnowflakeConnector:
        params = _load_connection_params(connection_name)
        conn = snowflake.connector.connect(**params)
        return cls(conn)

    @classmethod
    def connection_name_label(cls) -> str:
        return "Snowflake connection name"

    @classmethod
    def list_available_connections(cls) -> list[str]:
        toml_path = _resolve_config_toml()
        if toml_path is None or not toml_path.exists():
            return []
        try:
            with toml_path.open("rb") as f:
                data = tomllib.load(f)
            return sorted(data.get("connections", {}).keys())
        except Exception:
            return []

    @classmethod
    def default_connection_name(cls) -> str | None:
        toml_path = _resolve_config_toml()
        if toml_path is None or not toml_path.exists():
            return None
        try:
            with toml_path.open("rb") as f:
                data = tomllib.load(f)
            return data.get("default_connection_name")
        except Exception:
            return None

    def list_schemas(self, database: str) -> list[str]:
        db = _safe_identifier(database)
        sql = f"""
            SELECT schema_name
            FROM {db}.INFORMATION_SCHEMA.SCHEMATA
            WHERE schema_name != 'INFORMATION_SCHEMA'
            ORDER BY schema_name
        """
        with self._conn.cursor() as cur:
            cur.execute(sql)
            return [row[0] for row in cur.fetchall()]

    def list_objects(
        self,
        database: str,
        schemas: list[str] | None = None,
    ) -> list[SnowflakeObject]:
        db = _safe_identifier(database)
        schema_clause = ""
        if schemas:
            quoted = ", ".join(f"'{_safe_identifier(s)}'" for s in schemas)
            schema_clause = f"AND table_schema IN ({quoted})"

        tables_sql = f"""
            SELECT table_catalog, table_schema, table_name, table_type
            FROM {db}.INFORMATION_SCHEMA.TABLES
            WHERE table_schema != 'INFORMATION_SCHEMA'
            {schema_clause}
            ORDER BY table_schema, table_name
        """

        results: list[SnowflakeObject] = []

        with self._conn.cursor() as cur:
            try:
                cur.execute(tables_sql)
                for row in cur.fetchall():
                    try:
                        obj_type = SnowflakeObjectType(row[3])
                    except ValueError:
                        continue
                    results.append(
                        SnowflakeObject(
                            database=row[0].upper(),
                            schema=row[1].upper(),
                            name=row[2].upper(),
                            object_type=obj_type,
                        )
                    )
            except ProgrammingError as exc:
                if "too much data" in str(exc).lower():
                    results.extend(self._list_objects_by_schema(db, schema_clause, schemas))
                else:
                    raise

        # Dynamic tables are not in INFORMATION_SCHEMA.TABLES
        dt_schema_clause = schema_clause.replace("table_schema", "schema_name")
        dt_sql = f"""
            SELECT database_name, schema_name, name
            FROM TABLE({db}.INFORMATION_SCHEMA.DYNAMIC_TABLES())
            WHERE schema_name != 'INFORMATION_SCHEMA'
            {dt_schema_clause}
            ORDER BY schema_name, name
        """
        with self._conn.cursor() as cur:
            try:
                cur.execute(dt_sql)
                for row in cur.fetchall():
                    results.append(
                        SnowflakeObject(
                            database=row[0].upper(),
                            schema=row[1].upper(),
                            name=row[2].upper(),
                            object_type=SnowflakeObjectType.DYNAMIC_TABLE,
                        )
                    )
            except ProgrammingError:
                # Role lacks MONITOR privilege or dynamic tables not available
                pass

        return results

    def _list_objects_by_schema(
        self,
        db: str,
        schema_clause: str,
        schemas: list[str] | None,
    ) -> list[SnowflakeObject]:
        """Fallback: query schema-by-schema when TABLES returns 'too much data'."""
        all_schemas = schemas or self.list_schemas(db)
        results: list[SnowflakeObject] = []
        for schema in all_schemas:
            s = _safe_identifier(schema)
            sql = f"""
                SELECT table_catalog, table_schema, table_name, table_type
                FROM {db}.INFORMATION_SCHEMA.TABLES
                WHERE table_schema = '{s}'
                ORDER BY table_name
            """
            with self._conn.cursor() as cur:
                cur.execute(sql)
                for row in cur.fetchall():
                    try:
                        obj_type = SnowflakeObjectType(row[3])
                    except ValueError:
                        continue
                    results.append(
                        SnowflakeObject(
                            database=row[0].upper(),
                            schema=row[1].upper(),
                            name=row[2].upper(),
                            object_type=obj_type,
                        )
                    )
        return results

    def close(self) -> None:
        self._conn.close()
