"""M5 tests: the calendar SPA page is served and wired to the right API.

The page is vanilla JS rendered in the browser, so these tests verify what a
server-side test can: the route serves HTML, the FullCalendar resource
timeline + GPL license key are present, and the script's API wiring points at
the real endpoints (the JS builds URLs from a single `API` constant, so we
assert the constant and each path fragment).
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app
from scripts.seed import seed_database


@pytest.fixture()
def client(tmp_path):
    application = create_app(tmp_path / "spa.duckdb", seed_if_empty=False)
    seed_database(application.state.db, reference=datetime.now(timezone.utc))
    with TestClient(application) as c:
        yield c


@pytest.fixture()
def html(client):
    response = client.get("/session_schedule/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    return response.text


def test_calendar_mount_and_fullcalendar_cdn(html):
    assert 'id="calendar"' in html
    # FullCalendar Scheduler bundle from CDN, resource-timeline view, GPL key.
    assert "cdn.jsdelivr.net/npm/fullcalendar-scheduler" in html
    assert "resourceTimelineWeek" in html
    assert "schedulerLicenseKey: 'GPL-My-Project-Is-Open-Source'" in html
    # Instruments become the timeline's resource rows.
    assert "resources: instruments.map" in html


def test_page_wires_the_real_api_paths(html):
    # All fetch URLs are built from this constant...
    assert "const API = '/session_schedule/api'" in html
    # ...and each endpoint the page depends on is referenced.
    for fragment in [
        "${API}/scheduled-procedures",
        "${API}/procedure-types",
        "${API}/instruments",
        "${API}/mice",
        "${API}/projects",
        "${API}/users",
        "${API}/admin/scheduled-procedures",
    ]:
        assert fragment in html, f"missing API wiring: {fragment}"


def test_page_has_filters_legend_detail_panel_and_form(html):
    # Client-side filters: platform, instrument, date range, subject text.
    for element_id in [
        'id="filter-type"', 'id="filter-instrument"', 'id="filter-start"',
        'id="filter-end"', 'id="filter-subject"', 'id="legend"',
        'id="detail-panel"', 'id="add-btn"', 'id="procedure-form"',
        'id="active-types"', 'id="form-error"',
    ]:
        assert element_id in html, f"missing element: {element_id}"
    # Type checkboxes are constrained by the selected instrument's
    # compatible set (from the instruments endpoint).
    assert "compatible_procedure_types" in html
    # Color mapping is stable via procedure_types.sort_order.
    assert "sort_order" in html


def test_edit_path_never_echoes_server_computed_fields(html):
    """The write body is constructed field-by-field; the page must not PUT a
    read payload back verbatim (extra='forbid' would 422)."""
    assert "const body = {" in html
    for forbidden in ['"acquisition_type"', "body.id =", "created_at:", "updated_at:"]:
        assert forbidden not in html


def test_trailing_slash_and_root_redirects(client):
    bare = client.get("/session_schedule", follow_redirects=False)
    assert bare.status_code in (301, 307)
    assert bare.headers["location"].endswith("/session_schedule/")

    root = client.get("/", follow_redirects=False)
    assert root.status_code in (301, 307)
    assert root.headers["location"] == "/session_schedule/"


def test_page_not_in_openapi_schema(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/session_schedule/" not in paths
