from __future__ import annotations

import argparse

from dbt_cleaner.app import DbtCleanerApp


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dbt-cleaner",
        description="Find and remove orphaned Snowflake objects not tracked by any dbt manifest.",
    )
    parser.add_argument(
        "--connection",
        "-c",
        metavar="NAME",
        help="Snowflake connection name from config.toml (pre-fills config screen)",
    )
    parser.add_argument(
        "--database",
        "-d",
        action="append",
        dest="databases",
        metavar="DB",
        help="Snowflake database to scan (repeatable, pre-fills config screen)",
    )
    parser.add_argument(
        "--manifest",
        "-m",
        action="append",
        dest="manifests",
        metavar="PATH",
        help="Path to manifest.json (repeatable, pre-fills config screen)",
    )
    parser.add_argument(
        "--include-schema",
        action="append",
        dest="include_schemas",
        metavar="SCHEMA",
        help="Only scan these schemas (repeatable)",
    )
    parser.add_argument(
        "--exclude-schema",
        action="append",
        dest="exclude_schemas",
        metavar="SCHEMA",
        help="Skip these schemas (repeatable)",
    )
    args = parser.parse_args()

    app = DbtCleanerApp(
        connection_name=args.connection,
        databases=args.databases,
        manifest_paths=args.manifests,
        include_schemas=args.include_schemas,
        exclude_schemas=args.exclude_schemas,
    )
    result = app.run()

    # If user clicked "Print to stdout", app.exit(sql) returns the SQL here
    if isinstance(result, str):
        print(result)


if __name__ == "__main__":
    main()
