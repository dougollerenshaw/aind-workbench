"""M5 tests: the calendar SPA page is served and wired to the right API.

The page is vanilla JS rendered in the browser, so these tests verify what a
server-side test can: the route serves HTML, the FullCalendar resource
timeline + GPL license key are present, and the script's API wiring points at
the real endpoints (the JS builds URLs from a single `API` constant, so we
assert the constant and each path fragment).
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler_app.main import create_app
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


def test_default_view_is_a_single_day_opening_on_today(html):
    """The week view rendered 168 hourly columns, so "now" was far off-screen.
    The default is now one day at hour resolution, opened on today."""
    assert "initialView: 'resourceTimelineDay'" in html
    assert "initialDate: new Date()" in html
    # Live current-time line, and the initial scroll follows it.
    assert "nowIndicator: true" in html
    assert "scrollTime: nowScrollTime()" in html
    assert "function nowScrollTime" in html
    # The three view buttons are unchanged (no new agenda/list view).
    assert "resourceTimelineDay,resourceTimelineWeek,resourceTimelineMonth" in html
    assert "listWeek" not in html and "listMonth" not in html


def test_working_hours_window_is_a_named_adjustable_constant(html):
    match = re.search(
        r"const WORKING_HOURS = \{ start: '([\d:]+)', end: '([\d:]+)' \};", html
    )
    assert match, "WORKING_HOURS must be a single named constant"
    start, end = match.groups()
    assert start < end
    # Applied to the day view only, so week/month never hide events.
    day_config = html[html.index("function dayViewConfig") : html.index("function calendarViews")]
    assert "config.slotMinTime = WORKING_HOURS.start" in day_config
    assert "config.slotMaxTime = WORKING_HOURS.end" in day_config
    views = html[html.index("function calendarViews") : html.index("function nowScrollTime")]
    # No slot-range *assignment* in the week/month configs (comments are fine),
    # so those views can never clip an event out of existence.
    assert not re.search(r"slot(Min|Max)Time\s*:", views), "week/month must not clip events"


def test_out_of_window_procedures_are_reported_not_silently_hidden(html):
    """FullCalendar won't draw events outside slotMinTime..slotMaxTime, so the
    page must both warn about them and offer a way to see them."""
    assert 'id="window-notice"' in html
    assert "function updateWindowNotice" in html
    assert "are not drawn here" in html
    # The 24-hour escape hatch.
    assert 'id="full-day-toggle"' in html
    assert "function toggleFullDay" in html
    assert "calendar.setOption('views', calendarViews())" in html
    # Recomputed when the view or date range changes.
    assert "datesSet: () => updateWindowNotice(lastRecords)" in html


def test_week_and_month_use_day_resolution_columns(html):
    """A week is 7 day-columns, not 168 hour-columns; a month is ~30."""
    views = html[html.index("function calendarViews") : html.index("function nowScrollTime")]
    week = views[views.index("resourceTimelineWeek") : views.index("resourceTimelineMonth")]
    assert "slotDuration: { days: 1 }" in week
    month = views[views.index("resourceTimelineMonth") :]
    assert "slotDuration: { days: 1 }" in month
    # Day view keeps hour resolution.
    day_config = html[html.index("function dayViewConfig") : html.index("function calendarViews")]
    assert "slotDuration: '01:00:00'" in day_config
    # Time-of-day moves into the event label for the day-column views.
    assert "eventContent: (arg) => ({ text: eventLabel(arg.event) })" in html
    assert "function eventLabel" in html
    # Today's column is highlighted.
    assert ".fc-day-today" in html


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
    match = re.search(r"const body = \{(.*?)\};", html, re.S)
    assert match, "the form submit must build an explicit body object"
    body_block = match.group(1)
    # No server-computed fields in the constructed body...
    for field in ("acquisition_type", "created_at", "updated_at"):
        assert field not in body_block, f"body must not send {field}"
    # ...no bare `id:` key (mouse_id/project_id etc. are fine)...
    assert re.search(r"(?<![_a-zA-Z])id\s*:", body_block) is None
    # ...and no wholesale echo of a fetched record anywhere in the script.
    for echo in ("...currentDetail", "...record", "JSON.stringify(currentDetail)"):
        assert echo not in html
    # The only stringified request payload is the explicit body.
    assert "JSON.stringify(body)" in html


def test_detail_panel_renders_user_content_as_text(html):
    """User-typed fields (notes, protocols, planned_config) must be rendered
    via textContent, never innerHTML, so they can't inject markup."""
    renderer = html[html.index("async function showDetail") : html.index("function closeDetail")]
    # The only innerHTML use may be the empty-string clear of the <dl>.
    assignments = re.findall(r"innerHTML\s*=\s*([^;]+);", renderer)
    assert assignments and all(a.strip() == "''" for a in assignments)
    assert "textContent" in renderer


def test_hidden_toggled_elements_have_no_unguarded_display_rules(html):
    """Regression for the permanently-open modal (found in the first real
    browser pass): an author `display:` rule on an element toggled via the
    `hidden` attribute overrides the UA's `[hidden] { display: none }`, so
    the element can never be hidden. Every id the JS toggles via `.hidden`
    must either have no author display rule or guard it with [hidden] /
    :not([hidden])."""
    toggled = set(re.findall(r"getElementById\('([\w-]+)'\)\.hidden\s*=", html))
    assert {"modal-backdrop", "detail-panel"} <= toggled

    style = html[html.index("<style>") : html.index("</style>")]
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", style)
    for element_id in toggled:
        for selector, body in rules:
            for sel in selector.split(","):
                sel = sel.strip()
                # Rules that style the element ITSELF (not descendants — no
                # combinator), e.g. "#modal-backdrop", "#modal-backdrop:hover".
                if re.match(rf"#{element_id}(?![\w-])", sel) and " " not in sel:
                    if "display" in body:
                        assert "[hidden]" in sel, (
                            f"`{sel}` sets display without a [hidden] guard; "
                            f"the hidden attribute would stop working"
                        )
    # And the specific fix is present, so this exact regression can't return.
    assert "#modal-backdrop:not([hidden])" in style


def test_form_uses_start_plus_duration(html):
    """The form takes start + duration (hours); scheduled_end is computed
    client-side, keeping the API contract (start + end) unchanged."""
    assert 'id="f-duration"' in html
    assert 'type="number"' in html
    assert 'id="f-end"' not in html, "explicit end input was replaced by duration"
    # The submit body still sends a computed scheduled_end.
    match = re.search(r"const body = \{(.*?)\};", html, re.S)
    assert match and "scheduled_end: endDate.toISOString()" in match.group(1)
    # Edit mode derives duration from the record's end - start.
    assert "record.scheduled_end) - new Date(record.scheduled_start)" in html
    # Live hint shows the computed end time.
    assert 'id="end-hint"' in html
    assert "updateEndHint" in html


def test_date_filter_bounds_are_local_calendar_days(html):
    """The From/To inputs are local calendar dates, so the bounds sent to the
    API must be local midnight / end-of-day converted to UTC. Sending
    `${date}T00:00:00Z` shifted the window by the UTC offset and dropped real
    matches (in Pacific, a "To" date excluded everything after 16:59 local)."""
    assert "params.set('start_after', localDayStart(from).toISOString())" in html
    assert "params.set('start_before', localDayEnd(to).toISOString())" in html
    assert "function localDayStart" in html and "function localDayEnd" in html
    # No naive-UTC date bound is actually *sent* (the string may still appear
    # in the explanatory comment).
    assert not re.search(r"params\.set\([^)]*T00:00:00Z", html)
    assert not re.search(r"params\.set\([^)]*T23:59:59Z", html)


def test_behavior_exclusivity_wiring(html):
    """Once one Behavior-modality type is checked, the others are disabled and
    muted (mirrors the server's `multiple_behavior_types` rule)."""
    assert "const BEHAVIOR_MODALITY = 'Behavior'" in html
    assert "function applyBehaviorExclusivity" in html
    renderer = html[
        html.index("function applyBehaviorExclusivity") : html.index("function toLocalInputValue")
    ]
    # Filters the checkbox list by modality, then disables/mutes the rest.
    assert "dataset.modality === BEHAVIOR_MODALITY" in renderer
    assert "cb.disabled = muted" in renderer
    assert "opacity" in renderer
    # Modality comes from the API payload, not a hardcoded task list.
    assert "cb.dataset.modality = t.modality_name" in html
    # Re-applied whenever a checkbox changes and when the list is rebuilt.
    assert "cb.addEventListener('change', applyBehaviorExclusivity)" in html


def test_trailing_slash_and_root_redirects(client):
    bare = client.get("/session_schedule", follow_redirects=False)
    assert bare.status_code in (301, 307)
    assert bare.headers["location"].endswith("/session_schedule/")

    root = client.get("/", follow_redirects=False)
    assert root.status_code in (301, 307)
    assert root.headers["location"] == "/session_schedule/"


def test_page_not_in_openapi_schema(client):
    paths = client.get("/session_schedule/openapi.json").json()["paths"]
    assert "/session_schedule/" not in paths
