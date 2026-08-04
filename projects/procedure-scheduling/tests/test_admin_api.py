"""M4 tests: admin write API — validation rules, round-trips, atomicity.

Covers acceptance criteria 5 (compatibility validation), 6 (end > start),
and 7 (acquisition_type is server-computed, never client-supplied), plus
PUT/DELETE round-trips, atomic join updates, token immutability, and the
verifier advisory from M3: status-filter and next-acquisition behavior
against past-dated / completed / cancelled rows.
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler_app.main import create_app
from scripts.seed import seed_database

NOW = datetime.now(timezone.utc)
TODAY = NOW.replace(hour=0, minute=0, second=0, microsecond=0)

API = "/session_schedule/api"
ADMIN = f"{API}/admin"


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture()
def client(tmp_path):
    application = create_app(tmp_path / "admin.duckdb", seed_if_empty=False)
    seed_database(application.state.db, reference=NOW)
    with TestClient(application) as c:
        c.db = application.state.db
        yield c


def _id(client, table, column, value):
    return client.db.conn.execute(
        f"SELECT id FROM {table} WHERE {column} = ?", [value]
    ).fetchone()[0]


def _example_1_body(client, **overrides):
    """DESIGN.md Example 1: ephys + FIP on Ephys-Rig-2 (with real UUIDs)."""
    body = {
        "mouse_id": _id(client, "mice", "subject_id", "testmouse2"),
        "instrument_id": _id(client, "instruments", "name", "Ephys-Rig-2"),
        "project_id": _id(client, "projects", "name", "Cognitive flexibility in patch foraging"),
        "contact_user_id": _id(client, "users", "email", "doug.ollerenshaw@alleninstitute.org"),
        "experimenter_user_ids": [_id(client, "users", "email", "bruno.cruz@alleninstitute.org")],
        "scheduled_start": iso(TODAY + timedelta(days=30, hours=9)),
        "scheduled_end": iso(TODAY + timedelta(days=30, hours=11)),
        "active_procedure_type_ids": [
            _id(client, "procedure_types", "name",
                "Acute extracellular electrophysiology (modular insertion)"),
            _id(client, "procedure_types", "name", "Fiber photometry (FIP)"),
        ],
        "protocols": "Modular probe insertion, 4 shanks; FIP dual-fiber",
        "notes": "First ephys session for this mouse.",
        "planned_config": {"probe_count": 4, "fibers": ["DMS-left", "DMS-right"]},
    }
    body.update(overrides)
    return body


def _join_counts(client, sp_id):
    types = client.db.conn.execute(
        "SELECT count(*) FROM scheduled_procedure_active_types "
        "WHERE scheduled_procedure_id = ?", [sp_id],
    ).fetchone()[0]
    experimenters = client.db.conn.execute(
        "SELECT count(*) FROM scheduled_procedure_experimenters "
        "WHERE scheduled_procedure_id = ?", [sp_id],
    ).fetchone()[0]
    return types, experimenters


# ---------------------------------------------------------------------------
# POST — Example 1 worked case
# ---------------------------------------------------------------------------


def test_post_creates_scheduled_procedure_like_example_1(client):
    response = client.post(f"{ADMIN}/scheduled-procedures", json=_example_1_body(client))
    assert response.status_code == 201
    record = response.json()

    # Server-minted UUIDv7 token.
    assert record["id"].split("-")[2][0] == "7"
    # Server-computed acquisition_type (sorted + " + "-joined).
    assert record["acquisition_type"] == (
        "Acute extracellular electrophysiology (modular insertion) "
        "+ Fiber photometry (FIP)"
    )
    assert record["mouse"]["subject_id"] == "testmouse2"
    assert record["instrument"]["name"] == "Ephys-Rig-2"
    assert record["contact"]["name"] == "Doug Ollerenshaw"
    assert [e["name"] for e in record["experimenters"]] == ["Bruno Cruz"]
    assert record["acquisition_name"] is None
    assert record["status"] == "scheduled"
    assert record["planned_config"] == {"probe_count": 4, "fibers": ["DMS-left", "DMS-right"]}
    assert record["created_at"] == record["updated_at"]

    # Visible through the public read API, identically.
    assert client.get(f"{API}/scheduled-procedures/{record['id']}").json() == record
    # Join rows written (two active types, one experimenter).
    assert _join_counts(client, record["id"]) == (2, 1)


# ---------------------------------------------------------------------------
# Acceptance criterion 5 — compatibility validation
# ---------------------------------------------------------------------------


def test_incompatible_type_rejected_and_compatible_succeeds(client):
    histology = _id(client, "procedure_types", "name", "Whole-brain 3D histology")

    # Incompatible: histology on Ephys-Rig-2 -> documented 422 shape.
    before = client.db.conn.execute(
        "SELECT count(*) FROM scheduled_procedures"
    ).fetchone()[0]
    response = client.post(
        f"{ADMIN}/scheduled-procedures",
        json=_example_1_body(client, active_procedure_type_ids=[histology]),
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "incompatible_procedure_type"
    assert "'Whole-brain 3D histology' is not compatible with instrument 'Ephys-Rig-2'" in body["detail"]
    assert "Compatible types:" in body["detail"]
    after = client.db.conn.execute(
        "SELECT count(*) FROM scheduled_procedures"
    ).fetchone()[0]
    assert after == before, "a rejected write must not create a row"

    # Compatible: the same request with ephys + FIP succeeds.
    assert client.post(
        f"{ADMIN}/scheduled-procedures", json=_example_1_body(client)
    ).status_code == 201


# ---------------------------------------------------------------------------
# Acceptance criterion 6 — end must be strictly after start
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hours", [0, -2])
def test_end_not_after_start_rejected(client, hours):
    start = TODAY + timedelta(days=30, hours=9)
    response = client.post(
        f"{ADMIN}/scheduled-procedures",
        json=_example_1_body(
            client,
            scheduled_start=iso(start),
            scheduled_end=iso(start + timedelta(hours=hours)),
        ),
    )
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_time_range"


# ---------------------------------------------------------------------------
# Acceptance criterion 7 — acquisition_type is never client-supplied
# ---------------------------------------------------------------------------


def test_client_sent_acquisition_type_is_rejected(client):
    response = client.post(
        f"{ADMIN}/scheduled-procedures",
        json=_example_1_body(client) | {"acquisition_type": "Client-forged value"},
    )
    assert response.status_code == 422  # extra="forbid" — explicit rejection

    # And no row in the DB ever carries a non-computed value.
    forged = client.db.conn.execute(
        "SELECT count(*) FROM scheduled_procedures WHERE acquisition_type LIKE '%forged%'"
    ).fetchone()[0]
    assert forged == 0


@pytest.mark.parametrize("field", ["id", "created_at", "updated_at"])
def test_other_server_side_fields_rejected_in_body(client, field):
    response = client.post(
        f"{ADMIN}/scheduled-procedures",
        json=_example_1_body(client) | {field: "anything"},
    )
    assert response.status_code == 422


def test_post_with_duplicate_type_ids_dedupes_acquisition_type(client):
    """Regression (M4 verifier): a repeated active_procedure_type_id must not
    inflate acquisition_type — it is computed from the DEDUPED names, in
    lockstep with the deduped join-row inserts."""
    ephys = _id(client, "procedure_types", "name",
                "Acute extracellular electrophysiology (modular insertion)")
    fip = _id(client, "procedure_types", "name", "Fiber photometry (FIP)")

    response = client.post(
        f"{ADMIN}/scheduled-procedures",
        json=_example_1_body(client, active_procedure_type_ids=[ephys, ephys, fip, ephys]),
    )
    assert response.status_code == 201
    record = response.json()
    assert record["acquisition_type"] == (
        "Acute extracellular electrophysiology (modular insertion) "
        "+ Fiber photometry (FIP)"
    )
    assert record["active_procedure_types"] == [
        "Acute extracellular electrophysiology (modular insertion)",
        "Fiber photometry (FIP)",
    ]
    assert _join_counts(client, record["id"])[0] == 2  # one row per distinct type


def test_put_with_duplicate_type_ids_dedupes_acquisition_type(client):
    """Same regression through the PUT path, with a single repeated type."""
    created = client.post(
        f"{ADMIN}/scheduled-procedures", json=_example_1_body(client)
    ).json()
    fip = _id(client, "procedure_types", "name", "Fiber photometry (FIP)")

    response = client.put(
        f"{ADMIN}/scheduled-procedures/{created['id']}",
        json=_example_1_body(client, active_procedure_type_ids=[fip, fip, fip]),
    )
    assert response.status_code == 200
    record = response.json()
    assert record["acquisition_type"] == "Fiber photometry (FIP)"
    assert record["active_procedure_types"] == ["Fiber photometry (FIP)"]
    assert _join_counts(client, record["id"])[0] == 1


def test_acquisition_type_recomputed_on_put(client):
    created = client.post(
        f"{ADMIN}/scheduled-procedures", json=_example_1_body(client)
    ).json()
    # Drop FIP: recomputed to the single remaining type.
    ephys_only = _example_1_body(
        client,
        active_procedure_type_ids=[
            _id(client, "procedure_types", "name",
                "Acute extracellular electrophysiology (modular insertion)")
        ],
    )
    updated = client.put(
        f"{ADMIN}/scheduled-procedures/{created['id']}", json=ephys_only
    )
    assert updated.status_code == 200
    assert updated.json()["acquisition_type"] == (
        "Acute extracellular electrophysiology (modular insertion)"
    )


# ---------------------------------------------------------------------------
# PUT — round-trip, immutability, atomic join replacement
# ---------------------------------------------------------------------------


def test_put_round_trip_replaces_everything_but_id_and_created_at(client):
    created = client.post(
        f"{ADMIN}/scheduled-procedures", json=_example_1_body(client)
    ).json()
    time.sleep(0.01)  # so updated_at visibly advances

    new_body = {
        "mouse_id": _id(client, "mice", "subject_id", "testmouse1"),
        "instrument_id": _id(client, "instruments", "name", "VR-Foraging-Rig-A"),
        "project_id": _id(client, "projects", "name", "Brain-wide connectivity"),
        "contact_user_id": _id(client, "users", "email", "jane.kim@alleninstitute.org"),
        "experimenter_user_ids": [
            _id(client, "users", "email", "jane.kim@alleninstitute.org"),
            _id(client, "users", "email", "doug.ollerenshaw@alleninstitute.org"),
        ],
        "scheduled_start": iso(TODAY + timedelta(days=31, hours=13)),
        "scheduled_end": iso(TODAY + timedelta(days=31, hours=15)),
        "active_procedure_type_ids": [
            _id(client, "procedure_types", "name", "Dynamic foraging behavior"),
            _id(client, "procedure_types", "name", "Fiber photometry (FIP)"),
        ],
        "status": "rescheduled",
        "notes": "Moved to the VR rig.",
    }
    response = client.put(f"{ADMIN}/scheduled-procedures/{created['id']}", json=new_body)
    assert response.status_code == 200
    record = response.json()

    assert record["id"] == created["id"], "the token is immutable"
    assert record["created_at"] == created["created_at"]
    assert record["updated_at"] > created["updated_at"]
    assert record["mouse"]["subject_id"] == "testmouse1"
    assert record["instrument"]["name"] == "VR-Foraging-Rig-A"
    assert record["project"]["name"] == "Brain-wide connectivity"
    assert record["contact"]["name"] == "Jane Kim"
    assert [e["name"] for e in record["experimenters"]] == ["Doug Ollerenshaw", "Jane Kim"]
    assert record["acquisition_type"] == "Dynamic foraging behavior + Fiber photometry (FIP)"
    assert record["status"] == "rescheduled"
    # Full replace: fields omitted from the PUT body reset to null.
    assert record["planned_config"] is None
    assert record["protocols"] is None

    # Joins replaced exactly, no leftovers from the original row.
    assert _join_counts(client, record["id"]) == (2, 2)


def test_failed_put_leaves_record_and_joins_untouched(client):
    created = client.post(
        f"{ADMIN}/scheduled-procedures", json=_example_1_body(client)
    ).json()

    bad = _example_1_body(
        client,
        active_procedure_type_ids=[
            _id(client, "procedure_types", "name", "Whole-brain 3D histology")
        ],
        notes="should never land",
    )
    response = client.put(f"{ADMIN}/scheduled-procedures/{created['id']}", json=bad)
    assert response.status_code == 422
    assert response.json()["error"] == "incompatible_procedure_type"

    # Atomicity: the record is exactly as created — row fields AND join rows.
    assert client.get(f"{API}/scheduled-procedures/{created['id']}").json() == created
    assert _join_counts(client, created["id"]) == (2, 1)


def test_put_unknown_id_is_404(client):
    response = client.put(
        f"{ADMIN}/scheduled-procedures/no-such-id", json=_example_1_body(client)
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


def test_delete_removes_record_and_join_rows(client):
    created = client.post(
        f"{ADMIN}/scheduled-procedures", json=_example_1_body(client)
    ).json()
    assert _join_counts(client, created["id"]) == (2, 1)

    response = client.delete(f"{ADMIN}/scheduled-procedures/{created['id']}")
    assert response.status_code == 204

    assert client.get(f"{API}/scheduled-procedures/{created['id']}").status_code == 404
    assert _join_counts(client, created["id"]) == (0, 0)


def test_delete_unknown_id_is_404(client):
    assert client.delete(f"{ADMIN}/scheduled-procedures/no-such-id").status_code == 404


# ---------------------------------------------------------------------------
# Admin lookup creation
# ---------------------------------------------------------------------------


def test_create_instrument_with_compatibility_then_schedule_on_it(client):
    fip = _id(client, "procedure_types", "name", "Fiber photometry (FIP)")
    hsfp = _id(client, "procedure_types", "name", "Fiber photometry (HSFP)")

    response = client.post(
        f"{ADMIN}/instruments",
        json={
            "name": "FIP-Rig-9",
            "instrument_id": "FIP9",
            "sipe_rig_name": "BEH-FIP-09",
            "compatible_procedure_type_ids": [fip, hsfp],
        },
    )
    assert response.status_code == 201
    instrument = response.json()
    assert instrument["active"] is True
    assert {t["name"] for t in instrument["compatible_procedure_types"]} == {
        "Fiber photometry (FIP)", "Fiber photometry (HSFP)",
    }
    # Visible through the public read API.
    names = {i["name"] for i in client.get(f"{API}/instruments").json()}
    assert "FIP-Rig-9" in names

    # And schedulable, subject to its compatibility set.
    ok = client.post(
        f"{ADMIN}/scheduled-procedures",
        json=_example_1_body(
            client,
            instrument_id=instrument["id"],
            active_procedure_type_ids=[fip, hsfp],
        ),
    )
    assert ok.status_code == 201
    rejected = client.post(
        f"{ADMIN}/scheduled-procedures",
        json=_example_1_body(
            client,
            instrument_id=instrument["id"],
            active_procedure_type_ids=[
                _id(client, "procedure_types", "name", "Dynamic foraging behavior")
            ],
        ),
    )
    assert rejected.status_code == 422


def test_create_mouse_project_user(client):
    mouse = client.post(
        f"{ADMIN}/mice", json={"subject_id": "testmouse4", "genotype": "test-genotype"}
    )
    assert mouse.status_code == 201
    assert client.get(f"{API}/mice", params={"subject_id": "testmouse4"}).json()[0][
        "id"
    ] == mouse.json()["id"]

    project = client.post(f"{ADMIN}/projects", json={"name": "Test project"})
    assert project.status_code == 201

    user = client.post(
        f"{ADMIN}/users",
        json={"name": "Test User", "email": "test.user@alleninstitute.org"},
    )
    assert user.status_code == 201
    assert user.json()["orcid"] is None


def test_duplicate_natural_keys_rejected(client):
    assert client.post(
        f"{ADMIN}/mice", json={"subject_id": "testmouse1"}
    ).status_code == 422
    assert client.post(
        f"{ADMIN}/projects", json={"name": "Brain-wide connectivity"}
    ).status_code == 422
    assert client.post(
        f"{ADMIN}/users",
        json={"name": "X", "email": "doug.ollerenshaw@alleninstitute.org"},
    ).status_code == 422
    assert client.post(
        f"{ADMIN}/instruments", json={"name": "Ephys-Rig-2"}
    ).status_code == 422
    body = client.post(f"{ADMIN}/mice", json={"subject_id": "testmouse1"}).json()
    assert body["error"] == "already_exists"


def test_add_compatibility_unlocks_previously_incompatible_write(client):
    ephys_rig = _id(client, "instruments", "name", "Ephys-Rig-2")
    dynamic = _id(client, "procedure_types", "name", "Dynamic foraging behavior")

    attempt = _example_1_body(client, active_procedure_type_ids=[dynamic])
    assert client.post(f"{ADMIN}/scheduled-procedures", json=attempt).status_code == 422

    response = client.post(
        f"{ADMIN}/instrument-compatibility",
        json={"instrument_id": ephys_rig, "procedure_type_id": dynamic},
    )
    assert response.status_code == 201

    assert client.post(f"{ADMIN}/scheduled-procedures", json=attempt).status_code == 201


def test_unknown_references_rejected(client):
    response = client.post(
        f"{ADMIN}/scheduled-procedures",
        json=_example_1_body(client, mouse_id="not-a-mouse"),
    )
    assert response.status_code == 422
    assert response.json()["error"] == "unknown_reference"

    response = client.post(
        f"{ADMIN}/instrument-compatibility",
        json={"instrument_id": "nope", "procedure_type_id": "nope"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Verifier advisory (from M3): status filter and next-acquisition against
# past-dated / completed / cancelled rows
# ---------------------------------------------------------------------------


@pytest.fixture()
def mouse_with_history(client):
    """A fresh mouse with: a completed past session, a cancelled future
    session (tomorrow 06:00), and a scheduled future session (day+40)."""
    mouse_id = client.post(
        f"{ADMIN}/mice", json={"subject_id": "testmouse9"}
    ).json()["id"]
    vr = _id(client, "instruments", "name", "VR-Foraging-Rig-A")
    dynamic = _id(client, "procedure_types", "name", "Dynamic foraging behavior")

    def make(start, end, status):
        response = client.post(
            f"{ADMIN}/scheduled-procedures",
            json=_example_1_body(
                client,
                mouse_id=mouse_id,
                instrument_id=vr,
                active_procedure_type_ids=[dynamic],
                scheduled_start=iso(start),
                scheduled_end=iso(end),
                status=status,
            ),
        )
        assert response.status_code == 201
        return response.json()["id"]

    past = make(TODAY - timedelta(days=3, hours=-9),
                TODAY - timedelta(days=3, hours=-11), "completed")
    cancelled = make(TODAY + timedelta(days=1, hours=6),
                     TODAY + timedelta(days=1, hours=8), "cancelled")
    upcoming = make(TODAY + timedelta(days=40, hours=9),
                    TODAY + timedelta(days=40, hours=11), "scheduled")
    return {"mouse_id": mouse_id, "past": past, "cancelled": cancelled,
            "upcoming": upcoming}


def test_status_filter_positively_narrows(client, mouse_with_history):
    completed = client.get(
        f"{API}/scheduled-procedures", params={"status": "completed"}
    ).json()
    assert [r["id"] for r in completed] == [mouse_with_history["past"]]

    cancelled = client.get(
        f"{API}/scheduled-procedures", params={"status": "cancelled"}
    ).json()
    assert [r["id"] for r in cancelled] == [mouse_with_history["cancelled"]]

    scheduled_ids = {
        r["id"]
        for r in client.get(
            f"{API}/scheduled-procedures", params={"status": "scheduled"}
        ).json()
    }
    assert mouse_with_history["past"] not in scheduled_ids
    assert mouse_with_history["cancelled"] not in scheduled_ids
    assert mouse_with_history["upcoming"] in scheduled_ids


def test_next_acquisition_skips_past_and_cancelled_rows(client, mouse_with_history):
    response = client.get(f"{API}/animals/testmouse9/next-acquisition")
    assert response.status_code == 200
    got = response.json()
    # Not the completed past row, not the cancelled row tomorrow — the
    # scheduled row at day+40 is the true "next".
    assert got["id"] == mouse_with_history["upcoming"]
    assert got["scheduled_start"] == iso(TODAY + timedelta(days=40, hours=9))


def test_next_acquisition_404_when_only_past_or_cancelled(client, mouse_with_history):
    # Remove the one genuinely upcoming row; past + cancelled remain.
    assert client.delete(
        f"{ADMIN}/scheduled-procedures/{mouse_with_history['upcoming']}"
    ).status_code == 204
    response = client.get(f"{API}/animals/testmouse9/next-acquisition")
    assert response.status_code == 404
