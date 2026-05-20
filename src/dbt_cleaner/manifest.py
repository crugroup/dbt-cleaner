from __future__ import annotations

import json
from pathlib import Path

from dbt_cleaner.models import DbtObject

_OBJECT_RESOURCE_TYPES = frozenset({"model", "snapshot", "seed"})


def _normalize_identifier(raw: str) -> str:
    """Strip surrounding double-quotes (case-sensitive quoted identifiers) and upper-case.

    Snowflake stores unquoted identifiers in UPPER CASE. dbt quoted identifiers like
    `"myModel"` are case-sensitive in Snowflake — strip the quotes and preserve case.
    For unquoted identifiers, upper-case to match Snowflake storage.
    """
    if raw.startswith('"') and raw.endswith('"') and len(raw) > 2:
        return raw[1:-1]
    return raw.upper()


def load_manifest(path: str | Path) -> list[DbtObject]:
    """Parse a single manifest.json. Returns DbtObjects for nodes that persist to DB."""
    data = json.loads(Path(path).read_text())
    objects: list[DbtObject] = []

    for node in data.get("nodes", {}).values():
        resource_type = node.get("resource_type", "")
        if resource_type not in _OBJECT_RESOURCE_TYPES:
            continue

        config = node.get("config", {})
        materialized = config.get("materialized")
        if materialized == "ephemeral":
            continue

        database = node.get("database")
        schema = node.get("schema")
        identifier = node.get("identifier") or node.get("name")

        if not database or not schema or not identifier:
            continue

        objects.append(
            DbtObject(
                database=_normalize_identifier(database),
                schema=_normalize_identifier(schema),
                identifier=_normalize_identifier(identifier),
                resource_type=resource_type,
                materialized=materialized,
                project_name=node.get("package_name", "unknown"),
            )
        )

    return objects


def load_manifests(paths: list[str | Path]) -> list[DbtObject]:
    """Load multiple manifests, deduplicating on (database, schema, identifier)."""
    seen: set[tuple[str, str, str]] = set()
    result: list[DbtObject] = []

    for path in paths:
        for obj in load_manifest(path):
            key = (obj.database, obj.schema, obj.identifier)
            if key not in seen:
                seen.add(key)
                result.append(obj)

    return result
