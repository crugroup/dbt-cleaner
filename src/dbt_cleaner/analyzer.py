from __future__ import annotations

from collections import defaultdict

from dbt_cleaner.models import AnalysisConfig, AnalysisResult, DbtObject, SnowflakeObject

_EXCLUDED_SCHEMAS = frozenset({"INFORMATION_SCHEMA"})


def analyze(
    config: AnalysisConfig,
    snowflake_objects: list[SnowflakeObject],
    dbt_objects: list[DbtObject],
    dynamic_tables_skipped: bool = False,
) -> AnalysisResult:
    """Identify orphaned Snowflake objects not covered by any dbt manifest.

    Schema classification (per database):
    - locked_schema: schema has at least one dbt object → individual orphan objects listed
    - orphan_schema: schema has zero dbt coverage → candidate for DROP SCHEMA CASCADE
    """
    dbs = {d.upper() for d in config.databases}

    # Build known set: (db, schema, identifier) triples from all dbt objects
    known: set[tuple[str, str, str]] = set()
    dbt_db_schemas: set[tuple[str, str]] = set()
    for obj in dbt_objects:
        if obj.database.upper() not in dbs:
            continue
        known.add((obj.database.upper(), obj.schema.upper(), obj.identifier.upper()))
        dbt_db_schemas.add((obj.database.upper(), obj.schema.upper()))

    # Filter Snowflake objects to target databases, exclude system schemas
    sf_in_dbs = [
        o for o in snowflake_objects if o.database.upper() in dbs and o.schema.upper() not in _EXCLUDED_SCHEMAS
    ]

    # Apply include/exclude schema filters (applied across all target databases)
    if config.include_schemas:
        include = {s.upper() for s in config.include_schemas}
        sf_in_dbs = [o for o in sf_in_dbs if o.schema.upper() in include]
    if config.exclude_schemas:
        exclude = {s.upper() for s in config.exclude_schemas}
        sf_in_dbs = [o for o in sf_in_dbs if o.schema.upper() not in exclude]

    # Group by (database, schema)
    by_db_schema: dict[tuple[str, str], list[SnowflakeObject]] = defaultdict(list)
    for obj in sf_in_dbs:
        by_db_schema[(obj.database.upper(), obj.schema.upper())].append(obj)

    orphan_schemas: list[tuple[str, str]] = []
    locked_schemas: list[tuple[str, str]] = []
    orphan_objects: list[SnowflakeObject] = []

    for (db, schema), objects in sorted(by_db_schema.items()):
        if (db, schema) in dbt_db_schemas:
            locked_schemas.append((db, schema))
            for obj in objects:
                if (obj.database.upper(), obj.schema.upper(), obj.name.upper()) not in known:
                    orphan_objects.append(obj)
        else:
            orphan_schemas.append((db, schema))

    return AnalysisResult(
        config=config,
        snowflake_objects=sf_in_dbs,
        dbt_objects=dbt_objects,
        orphan_objects=orphan_objects,
        orphan_schemas=orphan_schemas,
        locked_schemas=locked_schemas,
        dynamic_tables_skipped=dynamic_tables_skipped,
    )
