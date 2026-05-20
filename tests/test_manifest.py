import json
import tempfile
from pathlib import Path

from dbt_cleaner.manifest import load_manifest, load_manifests


def make_manifest(nodes: dict) -> Path:
    data = {"nodes": nodes, "sources": {}}
    f = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump(data, f)
    f.close()
    return Path(f.name)


def model_node(
    name: str,
    database: str = "MYDB",
    schema: str = "ANALYTICS",
    materialized: str = "table",
    resource_type: str = "model",
) -> dict:
    return {
        "unique_id": f"{resource_type}.proj.{name}",
        "resource_type": resource_type,
        "name": name,
        "identifier": name,
        "database": database,
        "schema": schema,
        "package_name": "proj",
        "config": {"materialized": materialized},
    }


def test_basic_model():
    path = make_manifest({"model.proj.orders": model_node("orders")})
    objs = load_manifest(path)
    assert len(objs) == 1
    assert objs[0].identifier == "ORDERS"
    assert objs[0].schema == "ANALYTICS"
    assert objs[0].database == "MYDB"


def test_ephemeral_excluded():
    path = make_manifest({"model.proj.eph": model_node("eph", materialized="ephemeral")})
    assert load_manifest(path) == []


def test_test_nodes_excluded():
    path = make_manifest({"test.proj.t": model_node("t", resource_type="test")})
    assert load_manifest(path) == []


def test_analysis_nodes_excluded():
    path = make_manifest({"analysis.proj.a": model_node("a", resource_type="analysis")})
    assert load_manifest(path) == []


def test_snapshot_included():
    path = make_manifest({"snapshot.proj.s": model_node("s", resource_type="snapshot")})
    assert len(load_manifest(path)) == 1


def test_seed_included():
    path = make_manifest({"seed.proj.s": model_node("s", resource_type="seed")})
    assert len(load_manifest(path)) == 1


def test_missing_database_skipped():
    node = model_node("x")
    node["database"] = None
    path = make_manifest({"model.proj.x": node})
    assert load_manifest(path) == []


def test_identifier_uppercased():
    node = model_node("MyModel")
    node["identifier"] = "MyModel"
    path = make_manifest({"model.proj.MyModel": node})
    objs = load_manifest(path)
    assert objs[0].identifier == "MYMODEL"


def test_quoted_identifier_preserves_case():
    node = model_node("MyModel")
    node["identifier"] = '"MyModel"'
    path = make_manifest({"model.proj.MyModel": node})
    objs = load_manifest(path)
    assert objs[0].identifier == "MyModel"


def test_load_manifests_deduplication():
    node = model_node("orders")
    p1 = make_manifest({"model.proj1.orders": node})
    p2 = make_manifest({"model.proj2.orders": node})
    objs = load_manifests([p1, p2])
    assert len(objs) == 1


def test_load_manifests_union():
    p1 = make_manifest({"model.proj.a": model_node("a")})
    p2 = make_manifest({"model.proj.b": model_node("b")})
    objs = load_manifests([p1, p2])
    assert len(objs) == 2
