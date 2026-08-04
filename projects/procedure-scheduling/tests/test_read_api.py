"""M3 tests: the read-only API — filters, resolved shapes, rig endpoints, 404s.

The database is seeded relative to the real current date (like production),
so expected values are computed from the same "today". Filter tests compare
each filtered response against a locally filtered copy of the unfiltered
list, so they hold on any run date despite the seed's weekend nudging.
"""

import sys
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

SUMMARY_KEYS = {
    "id", "mouse", "instrument", "project", "contact", "experimenters",
    "active_procedure_types", "acquisition_type", "acquisition_name",
    "scheduled_start", "scheduled_end", "status",
}
DETAIL_KEYS = SUMMARY_KEYS | {
    "ethics_review_id", "notes", "planned_config", "protocols",
    "created_at", "updated_at",
}


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@pytest.fixture()
def client(tmp_path):
    application = create_app(tmp_path / "api.duckdb", seed_if_empty=False)
    seed_database(application.state.db, reference=NOW)
    with TestClient(application) as c:
        c.db = application.state.db
        yield c


@pytest.fixture()
def full(client):
    """The unfiltered scheduled-procedures list."""
    response = client.get(f"{API}/scheduled-procedures")
    assert response.status_code == 200
    return response.json()


def _lookup_id(client, table, column, value):
    return client.db.conn.execute(
        f"SELECT id FROM {table} WHERE {column} = ?", [value]
    ).fetchone()[0]


# ---------------------------------------------------------------------------
# List shape (DESIGN.md Example 2)
# ---------------------------------------------------------------------------


def test_list_returns_all_seeded_rows_sorted_by_start(full):
    assert len(full) == 18
    starts = [parse(r["scheduled_start"]) for r in full]
    assert starts == sorted(starts)


def test_sp1_payload_matches_example_2_shape(client, full):
    """SP-1 resolved exactly as documented (ids are real UUIDs here)."""
    sp1_start = iso(TODAY + timedelta(days=1, hours=9))
    sp1 = next(
        r for r in full
        if r["scheduled_start"] == sp1_start
        and r["instrument"]["name"] == "VR-Foraging-Rig-A"
    )
    assert set(sp1.keys()) == SUMMARY_KEYS

    assert sp1["mouse"] == {
        "id": _lookup_id(client, "mice", "subject_id", "testmouse1"),
        "subject_id": "testmouse1",
    }
    assert sp1["instrument"] == {
        "id": _lookup_id(client, "instruments", "name", "VR-Foraging-Rig-A"),
        "name": "VR-Foraging-Rig-A",
        "sipe_rig_name": "BEH-VR-01",
    }
    assert sp1["project"] == {
        "id": _lookup_id(client, "projects", "name", "Cognitive flexibility in patch foraging"),
        "name": "Cognitive flexibility in patch foraging",
    }
    assert sp1["contact"] == {
        "id": _lookup_id(client, "users", "email", "doug.ollerenshaw@alleninstitute.org"),
        "name": "Doug Ollerenshaw",
    }
    assert sp1["experimenters"] == [
        {
            "id": _lookup_id(client, "users", "email", "bruno.cruz@alleninstitute.org"),
            "name": "Bruno Cruz",
        }
    ]
    assert sp1["active_procedure_types"] == [
        "Dynamic foraging behavior", "Fiber photometry (FIP)",
    ]
    assert sp1["acquisition_type"] == "Dynamic foraging behavior + Fiber photometry (FIP)"
    assert sp1["acquisition_name"] is None
    assert sp1["scheduled_end"] == iso(TODAY + timedelta(days=1, hours=11))
    assert sp1["status"] == "scheduled"


def test_datetimes_are_iso_8601_utc_with_z_suffix(full):
    for record in full:
        for field in ("scheduled_start", "scheduled_end"):
            assert record[field].endswith("Z")
            assert parse(record[field]).tzinfo is not None


# ---------------------------------------------------------------------------
# Filters — each one individually, verified against the unfiltered list
# ---------------------------------------------------------------------------


def _expect(client, full, params, predicate):
    """GET with params; the result must equal the locally filtered full list."""
    response = client.get(f"{API}/scheduled-procedures", params=params)
    assert response.status_code == 200
    got = [r["id"] for r in response.json()]
    expected = [r["id"] for r in full if predicate(r)]
    assert got == expected
    return got


def test_filter_by_mouse_id(client, full):
    mouse_id = _lookup_id(client, "mice", "subject_id", "testmouse1")
    got = _expect(client, full, {"mouse_id": mouse_id},
                  lambda r: r["mouse"]["id"] == mouse_id)
    assert 0 < len(got) < 18


def test_filter_by_subject_id(client, full):
    got = _expect(client, full, {"subject_id": "testmouse2"},
                  lambda r: r["mouse"]["subject_id"] == "testmouse2")
    assert 0 < len(got) < 18


def test_filter_by_instrument_id(client, full):
    instrument_id = _lookup_id(client, "instruments", "name", "SmartSPIM-1")
    got = _expect(client, full, {"instrument_id": instrument_id},
                  lambda r: r["instrument"]["id"] == instrument_id)
    assert 0 < len(got) < 18


def test_filter_by_project_id(client, full):
    project_id = _lookup_id(client, "projects", "name", "Brain-wide connectivity")
    got = _expect(client, full, {"project_id": project_id},
                  lambda r: r["project"]["id"] == project_id)
    assert 0 < len(got) < 18


def test_filter_by_contact_user_id(client, full):
    contact_id = _lookup_id(client, "users", "email", "jane.kim@alleninstitute.org")
    got = _expect(client, full, {"contact_user_id": contact_id},
                  lambda r: r["contact"]["id"] == contact_id)
    assert 0 < len(got) < 18


def test_filter_by_procedure_type_matches_any_active_type(client, full):
    fip_id = _lookup_id(client, "procedure_types", "name", "Fiber photometry (FIP)")
    got = _expect(
        client, full, {"procedure_type_id": fip_id},
        lambda r: "Fiber photometry (FIP)" in r["active_procedure_types"],
    )
    assert 0 < len(got) < 18
    # FIP never appears alone in the seed, so this exercised "any active type".
    multi = [r for r in full if r["id"] in got and len(r["active_procedure_types"]) > 1]
    assert multi


def test_filter_by_status(client, full):
    got = _expect(client, full, {"status": "scheduled"},
                  lambda r: r["status"] == "scheduled")
    assert len(got) == 18
    assert client.get(f"{API}/scheduled-procedures", params={"status": "completed"}).json() == []


def test_filter_invalid_status_is_422(client):
    response = client.get(f"{API}/scheduled-procedures", params={"status": "bogus"})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "param,field,keep",
    [
        ("start_after", "scheduled_start", lambda value, cutoff: value >= cutoff),
        ("start_before", "scheduled_start", lambda value, cutoff: value <= cutoff),
        ("end_after", "scheduled_end", lambda value, cutoff: value >= cutoff),
        ("end_before", "scheduled_end", lambda value, cutoff: value <= cutoff),
    ],
)
def test_each_date_bound_filter(client, full, param, field, keep):
    cutoff = TODAY + timedelta(days=8)
    got = _expect(client, full, {param: iso(cutoff)},
                  lambda r: keep(parse(r[field]), cutoff))
    # The cutoff bisects the seeded window, so the count must actually change.
    assert 0 < len(got) < 18


def test_filters_are_combinable(client, full):
    vr_id = _lookup_id(client, "instruments", "name", "VR-Foraging-Rig-A")
    fip_id = _lookup_id(client, "procedure_types", "name", "Fiber photometry (FIP)")
    cutoff = TODAY + timedelta(days=10)
    got = _expect(
        client, full,
        {"instrument_id": vr_id, "procedure_type_id": fip_id,
         "start_before": iso(cutoff), "status": "scheduled"},
        lambda r: (
            r["instrument"]["id"] == vr_id
            and "Fiber photometry (FIP)" in r["active_procedure_types"]
            and parse(r["scheduled_start"]) <= cutoff
            and r["status"] == "scheduled"
        ),
    )
    assert 0 < len(got) < 18


# ---------------------------------------------------------------------------
# Single record
# ---------------------------------------------------------------------------


def test_single_record_fully_resolved(client, full):
    sp1_start = iso(TODAY + timedelta(days=1, hours=9))
    sp1 = next(
        r for r in full
        if r["scheduled_start"] == sp1_start
        and r["instrument"]["name"] == "VR-Foraging-Rig-A"
    )
    detail = client.get(f"{API}/scheduled-procedures/{sp1['id']}")
    assert detail.status_code == 200
    record = detail.json()
    assert set(record.keys()) == DETAIL_KEYS
    # The summary fields agree with the list payload...
    for key in SUMMARY_KEYS:
        assert record[key] == sp1[key]
    # ...and the detail-only fields are present and resolved.
    assert record["protocols"] == "Dynamic foraging task v2; FIP dual-fiber"
    assert record["ethics_review_id"] == "IACUC-2109"
    assert record["planned_config"] == {
        "stage": "stage_final", "fibers": ["DMS-left", "DMS-right"],
    }
    assert record["created_at"].endswith("Z")
    assert record["updated_at"].endswith("Z")


def test_unknown_scheduled_procedure_is_404(client):
    response = client.get(f"{API}/scheduled-procedures/no-such-id")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Lookup endpoints
# ---------------------------------------------------------------------------


def test_procedure_types_endpoint(client):
    types = client.get(f"{API}/procedure-types").json()
    assert [t["sort_order"] for t in types] == list(range(1, 9))
    assert types[0] == {
        "id": types[0]["id"],
        "name": "Acute extracellular electrophysiology (modular insertion)",
        "modality_name": "Extracellular electrophysiology",
        "modality_abbreviation": "ecephys",
        "sort_order": 1,
    }


def test_instruments_endpoint_with_filters(client):
    instruments = client.get(f"{API}/instruments").json()
    assert [i["name"] for i in instruments] == [
        "Ephys-Rig-2", "SmartSPIM-1", "VR-Foraging-Rig-A",
    ]
    vr = next(i for i in instruments if i["name"] == "VR-Foraging-Rig-A")
    assert vr["instrument_id"] == "VRForaging1"
    assert vr["sipe_rig_name"] == "BEH-VR-01"
    assert vr["active"] is True
    assert [t["name"] for t in vr["compatible_procedure_types"]] == [
        "Fiber photometry (FIP)", "Patch foraging behavior", "Dynamic foraging behavior",
    ]  # sort_order 4, 6, 7

    assert len(client.get(f"{API}/instruments", params={"active": "true"}).json()) == 3
    assert client.get(f"{API}/instruments", params={"active": "false"}).json() == []

    fip_id = _lookup_id(client, "procedure_types", "name", "Fiber photometry (FIP)")
    fip_capable = client.get(
        f"{API}/instruments", params={"procedure_type_id": fip_id}
    ).json()
    assert {i["name"] for i in fip_capable} == {"Ephys-Rig-2", "VR-Foraging-Rig-A"}


def test_mice_projects_users_endpoints(client):
    mice = client.get(f"{API}/mice").json()
    assert [m["subject_id"] for m in mice] == ["testmouse1", "testmouse2", "testmouse3"]

    filtered = client.get(f"{API}/mice", params={"subject_id": "testmouse2"}).json()
    assert len(filtered) == 1 and filtered[0]["subject_id"] == "testmouse2"
    assert filtered[0]["genotype"] == "test-genotype"

    projects = client.get(f"{API}/projects").json()
    assert [p["name"] for p in projects] == [
        "Brain-wide connectivity", "Cognitive flexibility in patch foraging",
    ]

    users = client.get(f"{API}/users").json()
    assert [(u["name"], u["email"]) for u in users] == [
        ("Bruno Cruz", "bruno.cruz@alleninstitute.org"),
        ("Doug Ollerenshaw", "doug.ollerenshaw@alleninstitute.org"),
        ("Jane Kim", "jane.kim@alleninstitute.org"),
    ]
    assert users[0]["orcid"] is None


# ---------------------------------------------------------------------------
# Rig-facing endpoints
# ---------------------------------------------------------------------------


def test_rig_planned_acquisitions(client, full):
    start, end = TODAY, TODAY + timedelta(days=3)
    response = client.get(
        f"{API}/rig/BEH-VR-01/planned-acquisitions",
        params={"start": iso(start), "end": iso(end)},
    )
    assert response.status_code == 200
    got = response.json()

    expected = [
        {
            "id": r["id"],
            "subject_id": r["mouse"]["subject_id"],
            "acquisition_type": r["acquisition_type"],
            "scheduled_start": r["scheduled_start"],
            "scheduled_end": r["scheduled_end"],
        }
        for r in full
        if r["instrument"]["sipe_rig_name"] == "BEH-VR-01"
        and start <= parse(r["scheduled_start"]) < end
    ]
    assert got == expected
    # SP-1 (tomorrow 09:00) is always inside this window.
    sp1 = next(g for g in got if g["scheduled_start"] == iso(start + timedelta(days=1, hours=9)))
    assert sp1["subject_id"] == "testmouse1"
    assert sp1["acquisition_type"] == "Dynamic foraging behavior + Fiber photometry (FIP)"
    assert set(sp1.keys()) == {
        "id", "subject_id", "acquisition_type", "scheduled_start", "scheduled_end",
    }


def test_rig_id_falls_back_to_instrument_name(client):
    params = {"start": iso(TODAY), "end": iso(TODAY + timedelta(days=21))}
    by_sipe = client.get(f"{API}/rig/BEH-VR-01/planned-acquisitions", params=params).json()
    by_name = client.get(f"{API}/rig/VR-Foraging-Rig-A/planned-acquisitions", params=params).json()
    assert by_sipe == by_name
    assert len(by_sipe) > 0


def test_unknown_rig_is_404(client):
    assert client.get(f"{API}/rig/NO-SUCH-RIG/planned-acquisitions").status_code == 404


def test_acquisition_record_equals_scheduled_procedure_detail(client, full):
    sp_id = full[0]["id"]
    a = client.get(f"{API}/acquisitions/{sp_id}")
    b = client.get(f"{API}/scheduled-procedures/{sp_id}")
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()


def test_unknown_acquisition_is_404(client):
    assert client.get(f"{API}/acquisitions/no-such-id").status_code == 404


def test_next_acquisition_for_animal(client, full):
    response = client.get(f"{API}/animals/testmouse1/next-acquisition")
    assert response.status_code == 200
    got = response.json()

    upcoming = [
        r for r in full
        if r["mouse"]["subject_id"] == "testmouse1"
        and parse(r["scheduled_start"]) > NOW
        and r["status"] == "scheduled"
    ]
    soonest = min(upcoming, key=lambda r: parse(r["scheduled_start"]))
    assert got == {
        "id": soonest["id"],
        "subject_id": "testmouse1",
        "instrument": soonest["instrument"]["name"],
        "acquisition_type": soonest["acquisition_type"],
        "scheduled_start": soonest["scheduled_start"],
    }
    # And that soonest row is SP-1: tomorrow 09:00 on the VR rig.
    assert got["scheduled_start"] == iso(TODAY + timedelta(days=1, hours=9))
    assert got["instrument"] == "VR-Foraging-Rig-A"


def test_next_acquisition_unknown_animal_is_404(client):
    assert client.get(f"{API}/animals/nosuchmouse/next-acquisition").status_code == 404


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


def test_docs_and_openapi_reachable(client):
    # Docs live under the /session_schedule prefix so they work both
    # standalone and behind the tool launcher.
    assert client.get("/session_schedule/docs").status_code == 200
    openapi = client.get("/session_schedule/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert f"{API}/scheduled-procedures" in paths
    # The PUBLIC data API is read-only: every write method lives under the
    # separate /api/admin/ namespace (DESIGN.md's read/write split).
    for path, methods in paths.items():
        if not path.startswith(f"{API}/admin/"):
            assert set(methods).issubset({"get"}), f"{path} has non-GET methods"


def test_public_api_rejects_write_methods(client, full):
    sp_id = full[0]["id"]
    assert client.post(f"{API}/scheduled-procedures", json={}).status_code == 405
    assert client.put(f"{API}/scheduled-procedures/{sp_id}", json={}).status_code == 405
    assert client.delete(f"{API}/scheduled-procedures/{sp_id}").status_code == 405
