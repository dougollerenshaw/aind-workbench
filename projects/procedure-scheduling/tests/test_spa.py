"""M13 tests: the hand-rolled calendar grid page.

The grid is built in the browser by vanilla JS, so these tests verify what a
server-side test can: the page is served, it requests **no external assets**,
and its static markup + script source wire up the documented structure
(day/week blocks, instrument sub-rows, one shared scroll container, the
8am-6pm focus constants, today-at-top, now-indicator, empty-day toggle) and
still contain every behavior validated in earlier rounds (modal hidden-CSS
guard, duration -> scheduled_end, local-day filter bounds, behavior-type
exclusivity, no echo of server-computed fields, text-only detail rendering).

A static trace is weaker evidence than a browser for a from-scratch layout:
these tests prove the wiring exists and is internally consistent, not that it
*looks* right. Visual verification is Doug's.
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


def script_body(html):
    """The page's inline <script> source."""
    return html[html.index("<script>") : html.rindex("</script>")]


def style_body(html):
    return html[html.index("<style>") : html.index("</style>")]


def code_only(html):
    """The page with HTML/CSS/JS comments stripped.

    Used for "this library is gone" assertions: the comments deliberately
    explain *why* FullCalendar was removed, so the name legitimately appears
    in prose while no code may reference it.
    """
    without = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    without = re.sub(r"/\*.*?\*/", "", without, flags=re.S)
    return re.sub(r"^\s*//.*$", "", without, flags=re.M)


# ---------------------------------------------------------------------------
# Self-contained page (FullCalendar removed in M13)
# ---------------------------------------------------------------------------


def test_page_has_no_external_asset_requests(html):
    """Zero external requests: the page works with no internet access in the
    viewer's browser, which was a real demo risk while FullCalendar came from
    a CDN."""
    assert not re.search(r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//""", html), (
        "no element may load an asset from another host"
    )
    assert "@import" not in html
    assert not re.search(r"url\(\s*['\"]?(?:https?:)?//", html), "no remote url() in CSS"
    # The only href values are same-origin paths (the /docs link).
    for href in re.findall(r"""href\s*=\s*["']([^"']+)["']""", html):
        assert href.startswith("/"), href
    # FullCalendar is gone from the code (the comments still explain why).
    code = code_only(html)
    for remnant in [
        "fullcalendar", "FullCalendar", "schedulerLicenseKey",
        "resourceTimeline", "slotDuration", "slotMinTime", "nowIndicator",
        ".fc-", "eventContent", "addEventSource",
    ]:
        assert remnant not in code, f"FullCalendar remnant left behind: {remnant}"


def test_page_wires_the_real_api_paths(html):
    assert "const API = '/session_schedule/api'" in html
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


# ---------------------------------------------------------------------------
# Grid structure: day/week blocks with instrument sub-rows
# ---------------------------------------------------------------------------


def test_grid_uses_one_shared_scroll_container(html):
    """All blocks live in a single scroll container, so scrolling one scrolls
    them all — no per-block scrollbars."""
    assert 'id="grid-scroll"' in html
    assert 'id="grid-inner"' in html
    style = style_body(html)
    scroll_rule = re.search(r"#grid-scroll\s*\{([^}]*)\}", style)
    assert scroll_rule, "#grid-scroll must have a style rule"
    assert re.search(r"overflow\s*:\s*auto", scroll_rule.group(1))
    assert style.count("overflow: auto") == 1, "only the shared container scrolls"
    # Blocks are appended to that container's inner element, not given their own.
    assert "document.getElementById('grid-inner')" in html


def test_day_blocks_contain_instrument_subrows(html):
    """Vertical nesting is day -> instrument, which is why FullCalendar (one
    resource axis) was dropped."""
    js = script_body(html)
    assert "function buildBlock" in js
    assert "function buildInstrumentRow" in js
    block = js[js.index("function buildBlock") : js.index("function buildInstrumentRow")]
    assert "day-header" in block
    assert "for (const instrument of rows)" in block
    assert "buildInstrumentRow(block, instrument, records, geo)" in block
    row = js[js.index("function buildInstrumentRow") : js.index("function layoutDayBars")]
    assert "instrument-row" in row
    assert "instrument-label" in row
    assert "'lane ruled'" in row
    # Day header reads like "Wednesday August 5".
    assert "weekday: 'long', month: 'long', day: 'numeric'" in js


def test_day_view_focus_window_constants(html):
    """8am-6pm fills the viewport by default; the full 24 h still exists and is
    reachable by scrolling."""
    js = script_body(html)
    assert "const FOCUS_START_HOUR = 8;" in js
    assert "const FOCUS_END_HOUR = 18;" in js
    assert "const FOCUS_HOURS = FOCUS_END_HOUR - FOCUS_START_HOUR;" in js
    assert "const HOURS_PER_DAY = 24;" in js
    # Hour width is sized so FOCUS_HOURS fill the visible lane...
    assert "const unitWidth = available / FOCUS_HOURS;" in js
    # ...the lane still spans all 24 hours...
    assert "laneWidth: unitWidth * HOURS_PER_DAY" in js
    # ...and the initial scroll lands on the focus start hour.
    assert (
        "scroller.scrollLeft = viewMode === 'day' ? FOCUS_START_HOUR * geo.unitWidth : 0;"
        in js
    )


def test_day_bars_positioned_by_start_and_duration(html):
    js = script_body(html)
    layout = js[js.index("function layoutDayBars") : js.index("function layoutWeekBars")]
    assert "startHours * geo.unitWidth" in layout, "left edge = start time"
    assert "(endHours - startHours) * geo.unitWidth" in layout, "width = duration"
    assert "MIN_BAR_WIDTH" in layout, "very short procedures stay clickable"
    # Bars are colored by primary active platform (existing sort_order palette).
    assert "primaryTypeColor(record.active_procedure_types)" in js
    assert "const PALETTE = [" in js
    # Labels are set as text, never markup.
    assert "bar.textContent = label;" in js


def test_week_view_uses_seven_day_columns(html):
    """A full week fits with no horizontal scrolling: 7 columns sized to the
    available width exactly."""
    js = script_body(html)
    assert "const DAYS_PER_WEEK = 7;" in js
    week_metrics = js[js.index("function metrics") : js.index("function blockRange")]
    assert "const unitWidth = available / DAYS_PER_WEEK;" in week_metrics
    assert "unitCount: DAYS_PER_WEEK, laneWidth: available" in week_metrics, (
        "week lane must fit the viewport exactly (no horizontal scrolling)"
    )
    # Week blocks are weeks, stacked like day blocks, Monday-based.
    assert "function startOfWeek" in js
    assert "`Week of ${" in js
    # A bar sits in its day's column and carries its local time.
    week_bars = js[js.index("function layoutWeekBars") : js.index("function makeBar")]
    assert "index * geo.unitWidth" in week_bars
    assert "fmtTime(start)" in week_bars


def test_default_view_is_day(html):
    js = script_body(html)
    assert "let viewMode = 'day';" in js
    assert 'id="view-day" class="active"' in html
    assert 'id="view-week"' in html
    # Month view was dropped (see BUILD_NOTES) — no stray button for it.
    assert 'id="view-month"' not in html


def test_today_at_top_and_now_indicator(html):
    js = script_body(html)
    # Today's block is marked and scrolled to the top of the grid.
    assert "function scrollToToday" in js
    assert "'.day-block.is-today'" in js
    assert "scroller.scrollTop = Math.max(0, block.offsetTop - offset);" in js
    assert "scrollToToday();" in js
    assert "isCurrent" in js and "classList.add('is-today')" in js
    # A now-line is drawn on the current block and kept fresh.
    assert "function buildNowLine" in js
    assert "'now-line'" in js
    assert "if (block.isCurrent) body.appendChild(buildNowLine(block, geo));" in js
    assert "function positionNowLine" in js
    assert "setInterval(positionNowLine, 60000)" in js
    # Past blocks exist above today, so scrolling up reveals them.
    assert "const WINDOW_DAYS_BEFORE = 14;" in js
    assert "const WINDOW_DAYS_AFTER = 45;" in js
    assert "addDays(today, -WINDOW_DAYS_BEFORE)" in js


def test_sticky_axis_header_and_instrument_labels(html):
    """The hour/day axis stays visible while scrolling vertically, and the
    instrument names stay visible while scrolling horizontally."""
    style = style_body(html)
    axis = re.search(r"\.axis-header\s*\{([^}]*)\}", style)
    assert axis and "position: sticky" in axis.group(1) and "top: 0" in axis.group(1)
    label = re.search(r"\.instrument-label\s*\{([^}]*)\}", style)
    assert label and "position: sticky" in label.group(1) and "left: 0" in label.group(1)


def test_empty_blocks_shown_by_default_with_a_toggle_to_hide(html):
    js = script_body(html)
    assert 'id="hide-empty-toggle"' in html
    # Default shows empty days so gaps read as real calendar gaps.
    assert "let hideEmpty = false;" in js
    assert "if (hideEmpty && inBlock.length === 0) continue;" in js
    # Empty blocks are labelled rather than blank.
    assert "'no procedures'" in js


def test_instrument_filter_removes_subrows(html):
    """Filtering to a rig should drop the other rows entirely, not leave them
    empty — Doug's primary interaction."""
    js = script_body(html)
    visible = js[js.index("function visibleInstruments") : js.index("function metrics")]
    assert "document.getElementById('filter-instrument').value" in visible
    assert "instruments.filter((i) => i.id === selected)" in visible
    assert "const rows = visibleInstruments();" in js


def test_event_click_opens_the_detail_panel(html):
    js = script_body(html)
    assert (
        "bar.addEventListener('click', () => showDetail(record.id).catch(showFetchError));"
        in js
    )
    assert 'id="detail-panel"' in html


def test_page_has_filters_legend_detail_panel_and_form(html):
    for element_id in [
        'id="filter-type"', 'id="filter-instrument"', 'id="filter-start"',
        'id="filter-end"', 'id="filter-subject"', 'id="legend"',
        'id="detail-panel"', 'id="add-btn"', 'id="procedure-form"',
        'id="active-types"', 'id="form-error"', 'id="jump-today"',
    ]:
        assert element_id in html, f"missing element: {element_id}"
    assert "compatible_procedure_types" in html
    assert "sort_order" in html


# ---------------------------------------------------------------------------
# Guards carried forward from earlier rounds
# ---------------------------------------------------------------------------


def test_edit_path_never_echoes_server_computed_fields(html):
    """The write body is constructed field-by-field; the page must not PUT a
    read payload back verbatim (extra='forbid' would 422)."""
    match = re.search(r"const body = \{(.*?)\};", html, re.S)
    assert match, "the form submit must build an explicit body object"
    body_block = match.group(1)
    for field in ("acquisition_type", "created_at", "updated_at"):
        assert field not in body_block, f"body must not send {field}"
    assert re.search(r"(?<![_a-zA-Z])id\s*:", body_block) is None
    for echo in ("...currentDetail", "...record", "JSON.stringify(currentDetail)"):
        assert echo not in html
    assert "JSON.stringify(body)" in html


def test_detail_panel_renders_user_content_as_text(html):
    """User-typed fields (notes, protocols, planned_config) must be rendered
    via textContent, never innerHTML, so they can't inject markup."""
    renderer = html[html.index("async function showDetail") : html.index("function closeDetail")]
    assignments = re.findall(r"innerHTML\s*=\s*([^;]+);", renderer)
    assert assignments and all(a.strip() == "''" for a in assignments)
    assert "textContent" in renderer


def test_hidden_toggled_elements_have_no_unguarded_display_rules(html):
    """Regression for the permanently-open modal: an author `display:` rule on
    an element toggled via the `hidden` attribute overrides the UA's
    `[hidden] { display: none }`, so the element can never be hidden."""
    toggled = set(re.findall(r"getElementById\('([\w-]+)'\)\.hidden\s*=", html))
    assert {"modal-backdrop", "detail-panel"} <= toggled

    style = style_body(html)
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", style)
    for element_id in toggled:
        for selector, body in rules:
            for sel in selector.split(","):
                sel = sel.strip()
                if re.match(rf"#{element_id}(?![\w-])", sel) and " " not in sel:
                    if "display" in body:
                        assert "[hidden]" in sel, (
                            f"`{sel}` sets display without a [hidden] guard; "
                            f"the hidden attribute would stop working"
                        )
    assert "#modal-backdrop:not([hidden])" in style


def test_form_uses_start_plus_duration(html):
    """The form takes start + duration (hours); scheduled_end is computed
    client-side, keeping the API contract (start + end) unchanged."""
    assert 'id="f-duration"' in html
    assert 'type="number"' in html
    assert 'id="f-end"' not in html
    match = re.search(r"const body = \{(.*?)\};", html, re.S)
    assert match and "scheduled_end: endDate.toISOString()" in match.group(1)
    assert "record.scheduled_end) - new Date(record.scheduled_start)" in html
    assert 'id="end-hint"' in html
    assert "updateEndHint" in html


def test_date_filter_bounds_are_local_calendar_days(html):
    """From/To are local calendar dates, so the bounds sent to the API must be
    local midnight / end-of-day converted to UTC."""
    assert "params.set('start_after', localDayStart(from).toISOString())" in html
    assert "params.set('start_before', localDayEnd(to).toISOString())" in html
    assert "function localDayStart" in html and "function localDayEnd" in html
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
    assert "dataset.modality === BEHAVIOR_MODALITY" in renderer
    assert "cb.disabled = muted" in renderer
    assert "opacity" in renderer
    assert "cb.dataset.modality = t.modality_name" in html
    assert "cb.addEventListener('change', applyBehaviorExclusivity)" in html


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


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
