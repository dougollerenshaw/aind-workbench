"""Regression tests for concurrent reads (the M14 blank-page root cause).

The calendar page fires five bootstrap requests at once. FastAPI runs sync
endpoint functions in a threadpool, so those requests hit the store from
several threads simultaneously. While the whole app shared ONE
DuckDBPyConnection that interleaved their result state and returned rows of
the wrong shape — `fetch_instruments` raised
``IndexError: tuple index out of range`` — which 500'd the API and left the
page blank.

These tests run at the Python level (fast, no browser) and fail loudly if
per-thread read isolation regresses.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler_app.db import Database
from scheduler_app.main import create_app
from scripts.seed import seed_database

API = "/session_schedule/api"

# The exact set the page requests on load, in the same shape.
BOOTSTRAP_PATHS = [
    f"{API}/procedure-types",
    f"{API}/instruments",
    f"{API}/mice",
    f"{API}/projects",
    f"{API}/users",
]


@pytest.fixture()
def client(tmp_path):
    application = create_app(tmp_path / "concurrent.duckdb", seed_if_empty=False)
    seed_database(application.state.db, reference=datetime.now(timezone.utc))
    with TestClient(application) as c:
        c.db = application.state.db
        yield c


def test_bootstrap_requests_all_succeed_under_concurrency(client):
    """The five page-load requests, fired together, repeatedly."""

    def get(path):
        response = client.get(path)
        return path, response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=10) as pool:
        # Several rounds, because the corruption was timing-dependent.
        jobs = [pool.submit(get, p) for _ in range(12) for p in BOOTSTRAP_PATHS]
        results = [job.result() for job in jobs]

    for path, status, payload in results:
        assert status == 200, f"{path} -> {status}: {payload}"
        assert isinstance(payload, list) and payload, f"{path} returned {payload!r}"


def test_instrument_payloads_are_never_malformed_under_concurrency(client):
    """The specific crash: a row came back short, so `r[3]` blew up. Assert the
    full resolved shape every time."""
    expected_keys = {
        "id", "name", "instrument_id", "sipe_rig_name", "location", "active",
        "compatible_procedure_types",
    }

    def get_instruments():
        response = client.get(f"{API}/instruments")
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = [job.result() for job in [pool.submit(get_instruments) for _ in range(40)]]

    names = None
    for status, payload in results:
        assert status == 200, payload
        assert len(payload) == 4, f"expected 4 instruments, got {len(payload)}"
        for instrument in payload:
            assert set(instrument) == expected_keys, instrument
            assert isinstance(instrument["name"], str) and instrument["name"]
            assert isinstance(instrument["compatible_procedure_types"], list)
        # Identical answer every time — no cross-talk between threads.
        current = [i["name"] for i in payload]
        if names is None:
            names = current
        assert current == names


def test_mixed_endpoints_under_concurrency_stay_consistent(client):
    """Hammer read endpoints of different shapes together."""
    paths = BOOTSTRAP_PATHS + [
        f"{API}/scheduled-procedures",
        f"{API}/scheduled-procedures?status=scheduled",
        f"{API}/rig/BEH-DF-01/planned-acquisitions",
        f"{API}/animals/testmouse1/next-acquisition",
    ]

    def get(path):
        response = client.get(path)
        return path, response.status_code

    with ThreadPoolExecutor(max_workers=12) as pool:
        jobs = [pool.submit(get, p) for _ in range(8) for p in paths]
        for path, status in [job.result() for job in jobs]:
            assert status == 200, f"{path} -> {status}"


def test_reads_from_many_threads_hit_independent_cursors(tmp_path):
    """Store-level check: concurrent queries on one Database never interleave.

    Each thread runs a query whose row shape differs, so a shared result state
    shows up as wrong-width tuples rather than merely wrong values.
    """
    db = Database(tmp_path / "cursors.duckdb")
    seed_database(db, reference=datetime.now(timezone.utc))

    def wide():
        rows = db.conn.execute(
            "SELECT id, name, instrument_id, sipe_rig_name, location, active FROM instruments"
        ).fetchall()
        return {len(r) for r in rows}

    def narrow():
        rows = db.conn.execute("SELECT id FROM procedure_types").fetchall()
        return {len(r) for r in rows}

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs = [pool.submit(wide if i % 2 else narrow) for i in range(80)]
            widths = [job.result() for job in jobs]
        for observed in widths:
            assert observed in ({6}, {1}), f"interleaved result state: {observed}"
    finally:
        db.close()
