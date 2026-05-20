from typing import Protocol, runtime_checkable

from dbt_cleaner.models import SnowflakeObject


@runtime_checkable
class DatabaseConnector(Protocol):
    """Abstract interface for querying a data warehouse object catalog.

    All I/O methods are synchronous to accommodate blocking drivers (e.g.
    snowflake-connector-python). Callers should run these in a thread worker
    (e.g. Textual's @work(thread=True)) to avoid blocking the event loop.

    To add a new backend (Postgres, Databricks, etc.), create a new module
    under connectors/ implementing this Protocol — no other files change.
    """

    def list_schemas(self, database: str) -> list[str]:
        """Return all schema names visible to the current role in *database*.

        Names are returned in canonical (typically upper-case) form.
        INFORMATION_SCHEMA is always excluded.
        """
        ...

    def list_objects(
        self,
        database: str,
        schemas: list[str] | None = None,
    ) -> list[SnowflakeObject]:
        """Return table/view/dynamic-table objects in *database*.

        If *schemas* is non-empty, only objects in those schemas are returned.
        Schema names are matched case-insensitively.
        INFORMATION_SCHEMA is always excluded.
        """
        ...

    def close(self) -> None:
        """Release the underlying connection."""
        ...

    @classmethod
    def connection_name_label(cls) -> str:
        """Human-readable label for the connection identifier field in the UI."""
        ...

    @classmethod
    def list_available_connections(cls) -> list[str]:
        """Return connection names the user can choose from.

        Returns an empty list if the connector does not support enumeration.
        """
        ...
