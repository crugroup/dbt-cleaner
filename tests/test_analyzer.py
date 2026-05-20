from dbt_cleaner.analyzer import analyze
from dbt_cleaner.models import (
    AnalysisConfig,
    DbtObject,
    SnowflakeObject,
    SnowflakeObjectType,
)


def cfg(**kwargs: object) -> AnalysisConfig:
    defaults: dict = dict(
        connection_name="test",
        databases=["MYDB"],
        manifest_paths=[],
        include_schemas=[],
        exclude_schemas=[],
    )
    return AnalysisConfig(**{**defaults, **kwargs})


def sf(schema: str, name: str, t: SnowflakeObjectType = SnowflakeObjectType.BASE_TABLE) -> SnowflakeObject:
    return SnowflakeObject(database="MYDB", schema=schema, name=name, object_type=t)


def dbt(schema: str, identifier: str) -> DbtObject:
    return DbtObject(
        database="MYDB",
        schema=schema,
        identifier=identifier,
        resource_type="model",
        materialized="table",
        project_name="proj",
    )


def test_no_orphans():
    result = analyze(cfg(), [sf("ANALYTICS", "ORDERS")], [dbt("ANALYTICS", "ORDERS")])
    assert result.orphan_objects == []
    assert result.orphan_schemas == []


def test_orphan_object_in_mixed_schema():
    result = analyze(
        cfg(),
        [sf("ANALYTICS", "ORDERS"), sf("ANALYTICS", "STALE")],
        [dbt("ANALYTICS", "ORDERS")],
    )
    assert len(result.orphan_objects) == 1
    assert result.orphan_objects[0].name == "STALE"
    assert result.orphan_schemas == []


def test_orphan_schema_all_objects_orphaned():
    result = analyze(cfg(), [sf("OLD_SCHEMA", "TBL")], [])
    assert ("MYDB", "OLD_SCHEMA") in result.orphan_schemas
    assert result.orphan_objects == []


def test_orphan_schema_objects_excluded_from_objects_list():
    """Objects in orphan schemas must not also appear in orphan_objects."""
    result = analyze(cfg(), [sf("OLD_SCHEMA", "A"), sf("OLD_SCHEMA", "B")], [])
    assert result.orphan_schemas == [("MYDB", "OLD_SCHEMA")]
    assert result.orphan_objects == []


def test_case_insensitive_matching():
    result = analyze(
        cfg(databases=["mydb"]),
        [SnowflakeObject("MYDB", "ANALYTICS", "ORDERS", SnowflakeObjectType.BASE_TABLE)],
        [DbtObject("mydb", "analytics", "orders", "model", "table", "proj")],
    )
    assert result.orphan_objects == []


def test_different_database_not_counted():
    result = analyze(
        cfg(databases=["MYDB"]),
        [SnowflakeObject("OTHERDB", "SCHEMA", "TBL", SnowflakeObjectType.BASE_TABLE)],
        [],
    )
    assert result.orphan_objects == []
    assert result.orphan_schemas == []
    assert result.snowflake_objects == []


def test_information_schema_excluded():
    result = analyze(cfg(), [sf("INFORMATION_SCHEMA", "TABLES")], [])
    assert result.orphan_schemas == []
    assert result.orphan_objects == []


def test_include_schema_filter():
    result = analyze(
        cfg(include_schemas=["ANALYTICS"]),
        [sf("ANALYTICS", "A"), sf("OTHER", "B")],
        [],
    )
    assert result.orphan_schemas == [("MYDB", "ANALYTICS")]


def test_exclude_schema_filter():
    result = analyze(
        cfg(exclude_schemas=["OTHER"]),
        [sf("ANALYTICS", "A"), sf("OTHER", "B")],
        [],
    )
    assert result.orphan_schemas == [("MYDB", "ANALYTICS")]


def test_multi_project_union():
    dbt_objs = [
        DbtObject("MYDB", "ANALYTICS", "T1", "model", "table", "proj_a"),
        DbtObject("MYDB", "ANALYTICS", "T2", "model", "table", "proj_b"),
    ]
    result = analyze(
        cfg(),
        [sf("ANALYTICS", "T1"), sf("ANALYTICS", "T2"), sf("ANALYTICS", "T3")],
        dbt_objs,
    )
    assert len(result.orphan_objects) == 1
    assert result.orphan_objects[0].name == "T3"


def test_view_type_preserved():
    result = analyze(cfg(), [sf("OLD_SCHEMA", "V1", SnowflakeObjectType.VIEW)], [])
    assert ("MYDB", "OLD_SCHEMA") in result.orphan_schemas


def test_dynamic_table_in_mixed_schema():
    result = analyze(
        cfg(),
        [
            sf("ANALYTICS", "KNOWN_TABLE"),
            SnowflakeObject("MYDB", "ANALYTICS", "OLD_DT", SnowflakeObjectType.DYNAMIC_TABLE),
        ],
        [dbt("ANALYTICS", "KNOWN_TABLE")],
    )
    assert len(result.orphan_objects) == 1
    assert result.orphan_objects[0].name == "OLD_DT"
    assert result.orphan_objects[0].object_type == SnowflakeObjectType.DYNAMIC_TABLE


def test_multiple_databases():
    result = analyze(
        cfg(databases=["MYDB", "OTHERDB"]),
        [
            SnowflakeObject("MYDB", "SCHEMA_A", "T1", SnowflakeObjectType.BASE_TABLE),
            SnowflakeObject("OTHERDB", "SCHEMA_B", "T2", SnowflakeObjectType.BASE_TABLE),
        ],
        [],
    )
    assert ("MYDB", "SCHEMA_A") in result.orphan_schemas
    assert ("OTHERDB", "SCHEMA_B") in result.orphan_schemas


def test_locked_schemas_populated():
    result = analyze(cfg(), [sf("ANALYTICS", "ORDERS")], [dbt("ANALYTICS", "ORDERS")])
    assert ("MYDB", "ANALYTICS") in result.locked_schemas
