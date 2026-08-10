"""Regression tests for the tool launcher's dispatcher wiring.

Drives the real `launcher.application` (werkzeug DispatcherMiddleware with
all five tools mounted) in-process with werkzeug's test Client — no server,
no port. The scheduler is pointed at a throwaway DuckDB via the
SCHEDULER_DB env var (set BEFORE launcher is imported), so these tests
never touch the real data/procedure_scheduling.duckdb, and writes through
the dispatcher can be exercised safely.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from werkzeug.test import Client

LAUNCHER_DIR = Path(__file__).resolve().parent.parent

# tests/conftest.py already pointed SCHEDULER_DB at a throwaway path before any
# test module ran (launcher.py reads it at import time, and several modules
# import launcher — so whoever imports first must not decide the value).
# setdefault keeps this module runnable on its own without clobbering it.
_TMP_DIR = tempfile.mkdtemp(prefix="launcher-test-db-")
os.environ.setdefault("SCHEDULER_DB", str(Path(_TMP_DIR) / "launcher_test.duckdb"))

sys.path.insert(0, str(LAUNCHER_DIR))
import launcher  # noqa: E402  (imports all five tools' apps)


@pytest.fixture(scope="module")
def client():
    return Client(launcher.application)


def test_scheduler_db_override_took_effect():
    assert str(launcher.SCHEDULER_DB) == os.environ["SCHEDULER_DB"]
    assert "procedure-scheduling/data" not in str(launcher.SCHEDULER_DB)


def test_landing_page_lists_all_tools(client):
    response = client.get("/")
    assert response.status_code == 200
    for mount in ["/query_tool", "/fiber_schematic_viewer", "/upgrader",
                  "/iacuc_lookup", "/session_schedule"]:
        assert mount in response.text
    assert "Procedure Scheduler" in response.text


def test_scheduler_page_through_dispatcher(client):
    response = client.get("/session_schedule/")
    assert response.status_code == 200
    assert 'id="calendar"' in response.text


def test_scheduler_api_through_dispatcher_returns_seeded_rows(client):
    response = client.get("/session_schedule/api/scheduled-procedures")
    assert response.status_code == 200
    rows = response.json
    assert len(rows) > 0
    assert rows[0]["mouse"]["subject_id"].startswith("testmouse")


def test_scheduler_docs_through_dispatcher(client):
    assert client.get("/session_schedule/docs").status_code == 200
    assert client.get("/session_schedule/openapi.json").status_code == 200


def test_bare_prefix_redirects_to_slash(client):
    response = client.get("/session_schedule")
    assert response.status_code in (301, 307, 308)
    assert response.headers["Location"].endswith("/session_schedule/")


def test_admin_write_through_dispatcher(client):
    """POST through the dispatcher creates a procedure (against the
    throwaway DB) — the write path works end-to-end behind the launcher."""
    instruments = client.get("/session_schedule/api/instruments").json
    # Pick any instrument and one of ITS compatible types, so this test keeps
    # working when the seed's rig/task assignments change.
    rig = next(i for i in instruments if i["compatible_procedure_types"])
    procedure_type = rig["compatible_procedure_types"][0]
    body = {
        "mouse_id": client.get(
            "/session_schedule/api/mice?subject_id=testmouse1").json[0]["id"],
        "instrument_id": rig["id"],
        "project_id": client.get("/session_schedule/api/projects").json[0]["id"],
        "contact_user_id": client.get("/session_schedule/api/users").json[0]["id"],
        "experimenter_user_ids": [],
        "scheduled_start": "2026-10-01T16:00:00Z",
        "scheduled_end": "2026-10-01T18:00:00Z",
        "active_procedure_type_ids": [procedure_type["id"]],
        "notes": "created through the launcher dispatcher (regression test)",
    }
    response = client.post(
        "/session_schedule/api/admin/scheduled-procedures",
        data=json.dumps(body),
        content_type="application/json",
    )
    assert response.status_code == 201, response.text
    record = response.json
    assert record["acquisition_type"] == procedure_type["name"]
    assert record["id"].split("-")[2][0] == "7"  # UUIDv7 token

    # And it is readable back through the dispatcher.
    assert client.get(
        f"/session_schedule/api/scheduled-procedures/{record['id']}"
    ).status_code == 200


@pytest.mark.parametrize(
    "mount", ["/query_tool", "/fiber_schematic_viewer", "/upgrader", "/iacuc_lookup"]
)
def test_existing_tools_still_respond(client, mount):
    """The four pre-existing tools must not 5xx (imports and dispatch intact)."""
    response = client.get(mount, follow_redirects=True)
    assert response.status_code < 500, f"{mount} -> {response.status_code}"
