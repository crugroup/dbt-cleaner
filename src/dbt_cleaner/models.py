from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SnowflakeObjectType(StrEnum):
    BASE_TABLE = "BASE TABLE"
    VIEW = "VIEW"
    MATERIALIZED_VIEW = "MATERIALIZED VIEW"
    EXTERNAL_TABLE = "EXTERNAL TABLE"
    DYNAMIC_TABLE = "DYNAMIC TABLE"
    TEMPORARY_TABLE = "TEMPORARY TABLE"
    EVENT_TABLE = "EVENT TABLE"


@dataclass(frozen=True)
class SnowflakeObject:
    database: str
    schema: str
    name: str
    object_type: SnowflakeObjectType

    @property
    def fqn(self) -> str:
        return f"{self.database}.{self.schema}.{self.name}"

    def drop_sql(self) -> str:
        match self.object_type:
            case (
                SnowflakeObjectType.BASE_TABLE
                | SnowflakeObjectType.EXTERNAL_TABLE
                | SnowflakeObjectType.TEMPORARY_TABLE
                | SnowflakeObjectType.EVENT_TABLE
            ):
                return f"DROP TABLE IF EXISTS {self.fqn};"
            case SnowflakeObjectType.VIEW:
                return f"DROP VIEW IF EXISTS {self.fqn};"
            case SnowflakeObjectType.MATERIALIZED_VIEW:
                return f"DROP MATERIALIZED VIEW IF EXISTS {self.fqn};"
            case SnowflakeObjectType.DYNAMIC_TABLE:
                return f"DROP DYNAMIC TABLE IF EXISTS {self.fqn};"
            case _:
                return f"-- unknown type {self.object_type}: DROP TABLE IF EXISTS {self.fqn};"


@dataclass(frozen=True)
class DbtObject:
    database: str
    schema: str
    identifier: str
    resource_type: str
    materialized: str | None
    project_name: str


@dataclass
class AnalysisConfig:
    connection_name: str
    databases: list[str]  # one or more target databases
    manifest_paths: list[str]
    include_schemas: list[str] = field(default_factory=list)
    exclude_schemas: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    config: AnalysisConfig
    snowflake_objects: list[SnowflakeObject]
    dbt_objects: list[DbtObject]
    orphan_objects: list[SnowflakeObject]
    orphan_schemas: list[tuple[str, str]]  # (database, schema)
    locked_schemas: list[tuple[str, str]]  # (database, schema)
    dynamic_tables_skipped: bool = False
