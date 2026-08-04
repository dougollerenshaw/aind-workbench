"""M6 tests: Parquet export round-trip (acceptance criterion 9).

Seed a temp database, export, and re-read every file with pyarrow: row
counts must equal DuckDB's, column names must match the schema (DESIGN.md's
Dataverse-mapping field names), and representative values — including
tz-aware datetimes and the planned_config JSON — must survive.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import TABLES, Database
from scripts.export_parquet import export_parquet
from scripts.seed import seed_database

REFERENCE = datetime(2026, 8, 3, 17, 30, tzinfo=timezone.utc)

EXPECTED_COLUMNS = {
    "procedure_types": ["id", "name", "modality_name", "modality_abbreviation", "sort_order"],
    "instruments": ["id", "name", "instrument_id", "sipe_rig_name", "location", "active"],
    "instrument_compatible_types": ["instrument_id", "procedure_type_id"],
    "mice": ["id", "subject_id", "genotype"],
    "projects": ["id", "name"],
    "users": ["id", "name", "email", "orcid"],
    "scheduled_procedures": [
        "id", "mouse_id", "instrument_id", "project_id", "contact_user_id",
        "scheduled_start", "scheduled_end", "acquisition_type",
        "acquisition_name", "status", "ethics_review_id", "notes",
        "planned_config", "protocols", "created_at", "updated_at",
    ],
    "scheduled_procedure_active_types": ["scheduled_procedure_id", "procedure_type_id"],
    "scheduled_procedure_experimenters": ["scheduled_procedure_id", "user_id"],
}


@pytest.fixture()
def exported(tmp_path):
    db = Database(tmp_path / "export.duckdb")
    seed_database(db, reference=REFERENCE)
    out_dir = tmp_path / "parquet"
    counts = export_parquet(db, out_dir)
    yield db, out_dir, counts
    db.close()


def test_one_parquet_file_per_table(exported):
    _, out_dir, _ = exported
    assert sorted(p.name for p in out_dir.glob("*.parquet")) == sorted(
        f"{t}.parquet" for t in TABLES
    )
    assert len(TABLES) == 9


def test_row_counts_match_duckdb(exported):
    """Acceptance criterion 9: pyarrow re-read == DuckDB row counts."""
    db, out_dir, reported = exported
    for table in TABLES:
        duck_count = db.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        parquet_count = pq.read_table(out_dir / f"{table}.parquet").num_rows
        assert parquet_count == duck_count, table
        assert reported[table] == duck_count, table
        assert duck_count > 0, f"{table} should be populated by the seed"


def test_column_names_match_schema(exported):
    _, out_dir, _ = exported
    for table, expected in EXPECTED_COLUMNS.items():
        names = pq.read_table(out_dir / f"{table}.parquet").schema.names
        assert names == expected, table


def test_lookup_values_survive(exported):
    _, out_dir, _ = exported
    types = pq.read_table(out_dir / "procedure_types.parquet").to_pylist()
    assert {t["name"] for t in types} >= {
        "Dynamic foraging behavior", "Fiber photometry (FIP)", "Whole-brain 3D histology",
    }
    fip = next(t for t in types if t["name"] == "Fiber photometry (FIP)")
    assert fip["modality_name"] == "Fiber photometry"
    assert fip["modality_abbreviation"] == "fib"
    assert fip["sort_order"] == 4

    instruments = pq.read_table(out_dir / "instruments.parquet").to_pylist()
    ephys = next(i for i in instruments if i["name"] == "Ephys-Rig-2")
    assert ephys["instrument_id"] == "EPHYS2"
    assert ephys["sipe_rig_name"] == "EPHYS-02"
    assert ephys["active"] is True

    mice = pq.read_table(out_dir / "mice.parquet").to_pylist()
    assert {m["subject_id"] for m in mice} == {"testmouse1", "testmouse2", "testmouse3"}


def test_scheduled_procedures_values_survive(exported):
    """Tz-aware datetimes and planned_config JSON survive representably,
    and the exported values equal DuckDB's for the same row."""
    db, out_dir, _ = exported
    table = pq.read_table(out_dir / "scheduled_procedures.parquet")

    # Datetime columns keep their timezone (UTC-zoned Parquet timestamps).
    for field_name in ("scheduled_start", "scheduled_end", "created_at", "updated_at"):
        field_type = table.schema.field(field_name).type
        assert pa.types.is_timestamp(field_type), field_name
        assert field_type.tz is not None, f"{field_name} lost its timezone"

    rows = table.to_pylist()
    # Compare one row (SP-1: earliest UUIDv7 = first created) against DuckDB.
    sp1 = min(rows, key=lambda r: r["id"])
    duck = db.conn.execute(
        "SELECT scheduled_start, scheduled_end, acquisition_type, status, planned_config "
        "FROM scheduled_procedures WHERE id = ?",
        [sp1["id"]],
    ).fetchone()
    assert sp1["scheduled_start"].tzinfo is not None
    assert sp1["scheduled_start"] == duck[0]
    assert sp1["scheduled_end"] == duck[1]
    assert sp1["acquisition_type"] == duck[2] == (
        "Dynamic foraging behavior + Fiber photometry (FIP)"
    )
    assert sp1["status"] == duck[3] == "scheduled"

    # planned_config: exported as a JSON string, parseable, equal to DuckDB's.
    assert sp1["planned_config"] is not None
    assert json.loads(sp1["planned_config"]) == json.loads(duck[4])
    assert json.loads(sp1["planned_config"])["fibers"] == ["DMS-left", "DMS-right"]

    # And the instant is the seeded one: reference date + 1 day at 09:00 UTC.
    assert sp1["scheduled_start"].astimezone(timezone.utc) == datetime(
        2026, 8, 4, 9, 0, tzinfo=timezone.utc
    )


def test_join_tables_survive_and_reference_valid_ids(exported):
    _, out_dir, _ = exported
    procedures = {
        r["id"] for r in pq.read_table(out_dir / "scheduled_procedures.parquet").to_pylist()
    }
    types = {r["id"] for r in pq.read_table(out_dir / "procedure_types.parquet").to_pylist()}
    users = {r["id"] for r in pq.read_table(out_dir / "users.parquet").to_pylist()}
    instruments = {r["id"] for r in pq.read_table(out_dir / "instruments.parquet").to_pylist()}

    active = pq.read_table(out_dir / "scheduled_procedure_active_types.parquet").to_pylist()
    assert all(r["scheduled_procedure_id"] in procedures for r in active)
    assert all(r["procedure_type_id"] in types for r in active)

    experimenters = pq.read_table(out_dir / "scheduled_procedure_experimenters.parquet").to_pylist()
    assert all(r["scheduled_procedure_id"] in procedures for r in experimenters)
    assert all(r["user_id"] in users for r in experimenters)

    compat = pq.read_table(out_dir / "instrument_compatible_types.parquet").to_pylist()
    assert all(r["instrument_id"] in instruments for r in compat)
    assert all(r["procedure_type_id"] in types for r in compat)


def test_export_is_rerunnable(exported):
    """Re-exporting overwrites in place with identical counts."""
    db, out_dir, first = exported
    second = export_parquet(db, out_dir)
    assert second == first
    for table in TABLES:
        assert pq.read_table(out_dir / f"{table}.parquet").num_rows == first[table]
