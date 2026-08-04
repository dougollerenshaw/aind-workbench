#!/usr/bin/env python
"""Export every table to Parquet for portability and Dataverse backfill.

Writes ``data/parquet/<table>.parquet`` for each of the nine tables, using
DuckDB's native Parquet writer (``COPY ... TO``). Column names and values are
exactly the DuckDB schema — which DESIGN.md's "Backfill to Microsoft
Dataverse" table maps field-by-field onto Bruno's proposed Dataverse tables —
so when Dataverse is ready these files are the import payload and prototype
rows carry over instead of being re-entered.

The files are plain Parquet, readable with pyarrow/pandas/anything:

    import pyarrow.parquet as pq
    pq.read_table("data/parquet/scheduled_procedures.parquet")

Usage:
    uv run python scripts/export_parquet.py                # default DB -> data/parquet/
    uv run python scripts/export_parquet.py --db-path X --out-dir Y
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `uv run python scripts/export_parquet.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler_app.db import DEFAULT_DB_PATH, TABLES, Database  # noqa: E402

DEFAULT_OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "parquet"


def export_parquet(db: Database, out_dir: str | Path = DEFAULT_OUT_DIR) -> dict[str, int]:
    """Write one Parquet file per table into ``out_dir``.

    Returns {table_name: row_count} for what was written.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    for table in TABLES:
        path = out_dir / f"{table}.parquet"
        # DuckDB's native Parquet writer; TIMESTAMPTZ columns come out as
        # UTC-zoned Parquet timestamps and JSON columns as strings.
        db.conn.execute(
            f"COPY {table} TO '{str(path).replace(chr(39), chr(39) * 2)}' (FORMAT PARQUET)"
        )
        counts[table] = db.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export every table to Parquet (one file per table)."
    )
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH),
                        help=f"DuckDB file to export (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR),
                        help=f"output directory (default: {DEFAULT_OUT_DIR})")
    args = parser.parse_args()

    db = Database(args.db_path)
    try:
        counts = export_parquet(db, args.out_dir)
    finally:
        db.close()

    print(f"Exported {args.db_path} -> {args.out_dir}:")
    for table, count in counts.items():
        print(f"  {table:38s} {count:4d} rows -> {table}.parquet")


if __name__ == "__main__":
    main()
