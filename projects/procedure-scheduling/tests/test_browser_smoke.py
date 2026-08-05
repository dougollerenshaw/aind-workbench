"""Headless-browser smoke tests: assert on the RENDERED page, not its source.

Why this module exists: 133 static tests passed while the calendar rendered a
completely blank box in a real browser (M13/M14). Assertions on HTML *text*
cannot see a blank page — three of Doug's UI bugs were found by looking at the
screen, not by the suite. These tests drive real Firefox and assert on DOM
state after the page's own JavaScript has run, so a blank page fails the suite.

How it works, without adding dependencies (no selenium/playwright):

1. Start the real app on an ephemeral port against a temp seeded DB.
2. Run a tiny proxy that serves the real ``template.html`` with two small
   ``<script>`` blocks injected — an error recorder in ``<head>`` (before the
   page's own script, so syntax and async errors are both caught) and a DOM
   probe at the end of ``<body>`` — and forwards every other path to the app,
   so the page's absolute ``/session_schedule/api/...`` URLs resolve on the
   same origin. The page's own code is never modified.
3. Load it in headless Firefox with ``browser.dom.window.dump.enabled``, so
   the probe's findings arrive on stdout, and parse them.

Skips cleanly (with a reason) when no Firefox binary is present.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler_app.main import create_app
from scripts.seed import seed_database

PROJECT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = PROJECT_DIR / "template.html"

FIREFOX = shutil.which("firefox") or "/usr/bin/firefox"
pytestmark = pytest.mark.skipif(
    not Path(FIREFOX).exists(),
    reason="no Firefox binary found; browser smoke tests need one "
    "(they are the only tests that can see a blank page)",
)

# Injected before the page's own script: records anything that goes wrong.
ERROR_RECORDER = """
<script>
window.__errors = [];
window.addEventListener('error', function (e) {
  window.__errors.push('error: ' + (e.message || e.type));
});
window.addEventListener('unhandledrejection', function (e) {
  var r = e.reason;
  window.__errors.push('rejection: ' + ((r && r.message) ? r.message : r));
});
</script>
"""

# Injected at the end of <body>: waits for the page's async bootstrap, then
# reports what actually rendered. `dump()` lands on Firefox's stdout.
DOM_PROBE = """
<script>
(function () {
  var deadline = Date.now() + 15000;
  function unitLabels(selector) {
    return document.querySelectorAll(selector).length;
  }
  function currentView() {
    return document.getElementById('view-week').classList.contains('active')
      ? 'week' : 'day';
  }
  function probe() {
    var legend = document.querySelectorAll('#legend .chip').length;
    var rows = document.querySelectorAll('.instrument-row').length;
    var bars = document.querySelectorAll('.event-bar').length;
    // Wait for the full async bootstrap — bars arrive after the schedule
    // fetch, later than the legend and rows — and for the view under test.
    var viewReady = !window.__expectView || currentView() === window.__expectView;
    var ready = legend > 0 && rows > 0 && bars > 0 && viewReady;
    if (!ready && Date.now() < deadline) { setTimeout(probe, 200); return; }
    var report = {
      errors: window.__errors,
      legend_chips: legend,
      day_blocks: document.querySelectorAll('.day-block').length,
      instrument_rows: rows,
      event_bars: bars,
      axis_units: unitLabels('.axis-unit'),
      now_lines: document.querySelectorAll('.now-line').length,
      today_blocks: document.querySelectorAll('.day-block.is-today').length,
      banner_hidden: document.getElementById('grid-error').hidden,
      banner_text: document.getElementById('grid-error').textContent,
      status_text: document.getElementById('grid-status').textContent,
      first_bar_width: (function () {
        var bar = document.querySelector('.event-bar');
        return bar ? Math.round(bar.getBoundingClientRect().width) : 0;
      })(),
      // Sticky labels must be ON SCREEN while the lanes are scrolled right;
      // `position: sticky` on a full-width box silently does nothing, which
      // left the day headers invisible (M14).
      sticky_offsets: (function () {
        var scroller = document.getElementById('grid-scroll');
        var box = scroller.getBoundingClientRect();
        function offset(sel) {
          var el = document.querySelector(sel);
          if (!el) return null;
          var r = el.getBoundingClientRect();
          return { left: Math.round(r.left - box.left), width: Math.round(r.width) };
        }
        return {
          day_header_label: offset('.day-header-label'),
          instrument_label: offset('.instrument-label'),
          axis_corner: offset('.axis-corner')
        };
      })(),
      day_header_text: (function () {
        var el = document.querySelector('.day-header-label');
        return el ? el.textContent.trim() : '';
      })(),
      scroll_left: Math.round(document.getElementById('grid-scroll').scrollLeft),
      overflowing: (function () {
        var found = [];
        document.querySelectorAll('#calendar, #calendar *').forEach(function (el) {
          if (el.scrollWidth > el.clientWidth + 4) {
            found.push((el.id ? '#' + el.id : el.className || el.tagName) +
                       ' ' + el.scrollWidth + '>' + el.clientWidth);
          }
        });
        return found;
      })(),
      view: currentView()
    };
    dump('PROBE ' + JSON.stringify(report) + '\\n');
  }
  probe();
})();
</script>
"""

# Switch to the week view once the day view has finished rendering, then let
# the probe wait for the switch to take effect.
WEEK_CLICK = """
<script>
window.__expectView = 'week';
(function () {
  var deadline = Date.now() + 12000;
  function go() {
    if (document.querySelectorAll('.event-bar').length > 0) {
      document.getElementById('view-week').click();
    } else if (Date.now() < deadline) {
      setTimeout(go, 200);
    }
  }
  go();
})();
</script>
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Threaded(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _make_proxy(port: int, upstream: str, page_html: str) -> _Threaded:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, status, ctype, body):
            try:
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # Expected: the browser is terminated as soon as the probe
                # reports, sometimes mid-request.
                pass

        def do_GET(self):
            if self.path.rstrip("/") == "/session_schedule":
                self._reply(200, "text/html; charset=utf-8", page_html.encode())
                return
            try:
                with urlopen(f"{upstream}{self.path}", timeout=10) as up:
                    body, status = up.read(), up.status
                    ctype = up.headers.get("Content-Type", "application/json")
            except HTTPError as exc:
                body, status = exc.read(), exc.code
                ctype = exc.headers.get("Content-Type", "application/json")
            self._reply(status, ctype, body)

    return _Threaded(("127.0.0.1", port), Handler)


def _instrumented_page(extra_scripts: str = "") -> str:
    """The real template with observation-only scripts injected."""
    html = TEMPLATE.read_text()
    html = html.replace("<style>", ERROR_RECORDER + "<style>", 1)
    return html.replace("</body>", extra_scripts + DOM_PROBE + "</body>", 1)


def _firefox_profile(tmp_path: Path) -> Path:
    profile = tmp_path / "ffprof"
    profile.mkdir(exist_ok=True)
    (profile / "user.js").write_text(
        'user_pref("browser.dom.window.dump.enabled", true);\n'
        'user_pref("browser.shell.checkDefaultBrowser", false);\n'
        'user_pref("datareporting.policy.dataSubmissionEnabled", false);\n'
        'user_pref("toolkit.telemetry.enabled", false);\n'
    )
    return profile


def _render(tmp_path: Path, page_html: str, upstream: str, timeout: float = 60) -> dict:
    """Serve `page_html`, load it in headless Firefox, return the DOM probe.

    Firefox does not exit on its own, so the probe line is read from its stdout
    as it streams and the browser is then terminated — much faster than waiting
    out a subprocess timeout, and it keeps the whole test under a few seconds
    in the happy path.
    """
    proxy_port = _free_port()
    proxy = _make_proxy(proxy_port, upstream, page_html)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    stdout_lines: list[str] = []
    report = None
    process = None
    try:
        process = subprocess.Popen(
            [
                FIREFOX, "--headless", "--profile", str(_firefox_profile(tmp_path)),
                "--window-size", "1600,1200",
                f"http://127.0.0.1:{proxy_port}/session_schedule/",
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "MOZ_HEADLESS": "1"},
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue
            stdout_lines.append(line)
            match = re.match(r"^PROBE (\{.*\})\s*$", line)
            if match:
                report = json.loads(match.group(1))
                break
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                process.kill()
        proxy.shutdown()
        proxy.server_close()

    assert report is not None, (
        "the DOM probe never reported — the page did not finish rendering "
        "(this is what a blank page looks like).\nstdout:\n"
        + "".join(stdout_lines[-40:])
    )
    return report


@pytest.fixture(scope="module")
def app_server(tmp_path_factory):
    """The real app on an ephemeral port against a temp seeded DB."""
    tmp = tmp_path_factory.mktemp("browser-smoke")
    db_path = tmp / "browser.duckdb"
    application = create_app(db_path, seed_if_empty=False)
    seed_database(application.state.db, reference=datetime.now(timezone.utc))

    port = _free_port()
    config = uvicorn.Config(application, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/session_schedule/api/instruments", timeout=2):
                break
        except Exception:
            time.sleep(0.25)
    else:  # pragma: no cover
        pytest.fail("app server did not come up")

    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="module")
def day_view(app_server, tmp_path_factory):
    return _render(tmp_path_factory.mktemp("day"), _instrumented_page(), app_server)


@pytest.fixture(scope="module")
def week_view(app_server, tmp_path_factory):
    return _render(
        tmp_path_factory.mktemp("week"), _instrumented_page(WEEK_CLICK), app_server
    )


# ---------------------------------------------------------------------------
# The assertions that would have caught a blank page
# ---------------------------------------------------------------------------


def test_no_javascript_errors(day_view):
    assert day_view["errors"] == [], f"page raised JS errors: {day_view['errors']}"


def test_no_failure_banner(day_view):
    assert day_view["banner_hidden"] is True, (
        f"bootstrap reported a failure: {day_view['banner_text']}"
    )


def test_legend_renders_all_eight_platforms(day_view):
    assert day_view["legend_chips"] == 8


def test_day_view_renders_blocks_rows_and_bars(day_view):
    """The core anti-blank assertion."""
    assert day_view["day_blocks"] > 0, "no day blocks rendered"
    assert day_view["instrument_rows"] > 0, "no instrument sub-rows rendered"
    assert day_view["event_bars"] > 0, "no event bars rendered"
    # Sub-rows are blocks x instruments, so there are several per block.
    assert day_view["instrument_rows"] >= day_view["day_blocks"]
    # Bars have real width (a zero-width bar is invisible).
    assert day_view["first_bar_width"] > 4


def test_day_view_axis_is_24_hours_and_scrolled_to_the_focus_hour(day_view):
    assert day_view["axis_units"] == 24, "day axis should span the full 24 h"
    # Opens at 8am rather than midnight, so the working day is on screen.
    assert day_view["scroll_left"] > 0
    assert day_view["view"] == "day", "day view is the default"


def test_today_is_marked_and_has_a_now_line(day_view):
    assert day_view["today_blocks"] == 1
    assert day_view["now_lines"] == 1


def test_status_line_reports_loaded_procedures(day_view):
    assert re.search(r"\d+ procedure\(s\)", day_view["status_text"]), day_view["status_text"]


def test_sticky_labels_are_visible_while_lanes_are_scrolled(day_view):
    """The day view opens scrolled to 8am, so the day header, instrument names
    and axis corner must all still be on screen.

    This is the assertion that catches `position: sticky` applied to a
    full-width box, which does nothing and left the day-header text parked
    off-screen at the far left of a 3000px-wide element.
    """
    assert day_view["scroll_left"] > 0, "day view should be scrolled to the focus hour"
    offsets = day_view["sticky_offsets"]
    for name in ("day_header_label", "instrument_label", "axis_corner"):
        box = offsets[name]
        assert box is not None, f"{name} not rendered"
        # Left edge inside the scrollport (allow a pixel of rounding).
        assert -1 <= box["left"] <= 8, f"{name} is scrolled out of view: {box}"
        assert box["width"] > 20, f"{name} has no width: {box}"
    # And the header actually says which day it is.
    assert re.search(
        r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)",
        day_view["day_header_text"],
    ), day_view["day_header_text"]


def test_week_view_renders_seven_day_columns(week_view):
    assert week_view["errors"] == [], week_view["errors"]
    assert week_view["view"] == "week"
    assert week_view["axis_units"] == 7, "week axis should be 7 day columns"
    assert week_view["instrument_rows"] > 0
    assert week_view["event_bars"] > 0
    # A full week must fit: nothing in the calendar overflows horizontally.
    assert week_view["scroll_left"] == 0
    assert week_view["overflowing"] == [], (
        f"week view must not scroll horizontally: {week_view['overflowing']}"
    )
