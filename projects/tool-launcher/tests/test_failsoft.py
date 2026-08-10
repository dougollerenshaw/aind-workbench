"""The scheduler mount must fail SOFT: a broken scheduler cannot take the
other tools down.

Background: on 2026-08-10 `launcher.py` imported `scheduler_app` at module
scope. An edit in progress left that package referencing an undefined name, so
the import raised and killed the launcher process — query_tool,
fiber_schematic_viewer, upgrader and iacuc_lookup were all offline because of an
unrelated project's half-finished file.

The import is now deferred into `LazySchedulerApp._build` and guarded. These
tests drive the real mounts through werkzeug's test client with a deliberately
broken `_build`, asserting the blast radius is exactly one mount.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.test import Client

LAUNCHER_DIR = Path(__file__).resolve().parent.parent

# Point the scheduler at a throwaway DB before importing launcher (it reads
# SCHEDULER_DB at import time), so nothing here can touch the real database.
os.environ.setdefault(
    "SCHEDULER_DB", str(Path(tempfile.mkdtemp(prefix="failsoft-db-")) / "scratch.duckdb")
)

sys.path.insert(0, str(LAUNCHER_DIR))
import launcher  # noqa: E402

# The incident's exact error, reproduced.
INCIDENT_ERROR = NameError("name 'SubjectLookupOut' is not defined")

OTHER_MOUNTS = ["/query_tool", "/fiber_schematic_viewer", "/upgrader", "/iacuc_lookup"]


def _broken_scheduler_mount(exc=INCIDENT_ERROR):
    """A real LazySchedulerApp whose import/build always fails."""
    mount = launcher.LazySchedulerApp()

    def fail():
        raise exc

    mount._build = fail
    return mount


def _app_with(scheduler_mount):
    """The real launcher dispatcher, with the scheduler mount swapped.

    Building a fresh DispatcherMiddleware keeps the module-level mount (which
    other tests use) untouched.
    """
    return DispatcherMiddleware(
        launcher.root_app,
        {
            "/query_tool": launcher.query_app,
            "/fiber_schematic_viewer": launcher.fiber_app,
            "/upgrader": launcher.upgrader_app,
            "/iacuc_lookup": launcher.iacuc_app,
            "/session_schedule": scheduler_mount,
        },
    )


@pytest.fixture()
def broken_client():
    return Client(_app_with(_broken_scheduler_mount()))


# ---------------------------------------------------------------------------
# Blast radius
# ---------------------------------------------------------------------------


def test_landing_page_survives_a_broken_scheduler(broken_client):
    response = broken_client.get("/")
    assert response.status_code == 200
    assert "AIND Tools" in response.text


@pytest.mark.parametrize("mount", OTHER_MOUNTS)
def test_other_tools_survive_a_broken_scheduler(broken_client, mount):
    """The whole point: one broken project must not 5xx the others."""
    response = broken_client.get(mount, follow_redirects=True)
    assert response.status_code < 500, f"{mount} -> {response.status_code}"


def test_scheduler_serves_a_plain_text_503(broken_client):
    response = broken_client.get("/session_schedule/")
    assert response.status_code == 503
    # text/plain, never HTML: the exception text is data, not markup.
    assert response.headers["Content-Type"].startswith("text/plain")
    assert response.headers["Retry-After"]
    body = response.text
    assert "Procedure Scheduler unavailable" in body
    # Names the real cause so whoever sees it can act.
    assert "NameError" in body
    assert "SubjectLookupOut" in body
    # Points at the check that would have caught it.
    assert "from scheduler_app.main import create_app" in body


def test_error_page_does_not_render_exception_text_as_markup():
    """An exception carrying markup must not become markup."""
    mount = _broken_scheduler_mount(RuntimeError("<script>alert(1)</script>"))
    client = Client(_app_with(mount))
    response = client.get("/session_schedule/")
    assert response.status_code == 503
    assert response.headers["Content-Type"].startswith("text/plain")
    # Present as literal text; harmless because the content type is not HTML.
    assert "<script>alert(1)</script>" in response.text


# ---------------------------------------------------------------------------
# Retry behaviour: transient failures must recover without a restart, but a
# broken tree must not spin the log.
# ---------------------------------------------------------------------------


def test_failure_is_retried_after_the_backoff_window():
    mount = launcher.LazySchedulerApp()
    mount.RETRY_AFTER_SECONDS = 0        # collapse the window for the test
    attempts = {"n": 0}

    def build():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise INCIDENT_ERROR
        return _ok_wsgi_app

    mount._build = build
    client = Client(_app_with(mount))

    first = client.get("/session_schedule/")
    assert first.status_code == 503

    second = client.get("/session_schedule/")
    assert second.status_code == 200, "a fixed tree must recover without a restart"
    assert attempts["n"] == 2


def test_failure_is_not_retried_inside_the_backoff_window():
    """Otherwise every page refresh would re-import a broken tree."""
    mount = launcher.LazySchedulerApp()
    mount.RETRY_AFTER_SECONDS = 300
    attempts = {"n": 0}

    def build():
        attempts["n"] += 1
        raise INCIDENT_ERROR

    mount._build = build
    client = Client(_app_with(mount))

    for _ in range(5):
        assert client.get("/session_schedule/").status_code == 503
    assert attempts["n"] == 1, "should import once, then back off"


def _ok_wsgi_app(environ, start_response):
    """Stand-in for the built scheduler app."""
    body = b"scheduler ok"
    start_response("200 OK", [("Content-Type", "text/plain"),
                              ("Content-Length", str(len(body)))])
    return [body]


def test_successful_mount_still_rewrites_the_prefix():
    """The prefix shim must survive the fail-soft refactor: DispatcherMiddleware
    strips /session_schedule into SCRIPT_NAME and the scheduler needs it back."""
    seen = {}

    def capture(environ, start_response):
        seen["path"] = environ["PATH_INFO"]
        seen["script_name"] = environ["SCRIPT_NAME"]
        return _ok_wsgi_app(environ, start_response)

    mount = launcher.LazySchedulerApp()
    mount._build = lambda: capture
    client = Client(_app_with(mount))

    assert client.get("/session_schedule/api/instruments").status_code == 200
    assert seen["path"] == "/session_schedule/api/instruments"
    assert seen["script_name"] == ""


# ---------------------------------------------------------------------------
# Reloader scoping (the other half of the incident: test edits restart-looped
# the live service)
# ---------------------------------------------------------------------------


def test_reloader_excludes_tests_and_non_code_paths():
    patterns = launcher.RELOADER_EXCLUDE_PATTERNS
    for needed in ["*/tests/*", "*/test_*.py", "*/.venv/*", "*/__pycache__/*",
                   "*.pyc", "*/data/*"]:
        assert needed in patterns, f"reloader should ignore {needed}"


def test_reloader_patterns_match_the_files_that_caused_the_restart_loop():
    """The file named in Doug's restart-loop log must be excluded, while real
    source files must still trigger a reload."""
    from fnmatch import fnmatch

    project = LAUNCHER_DIR.parent / "procedure-scheduling"
    ignored = [
        project / "tests" / "test_browser_smoke.py",   # the actual culprit
        project / "tests" / "test_seed.py",
        project / "conftest.py",
        project / "data" / "procedure_scheduling.duckdb",
        project / ".venv" / "lib" / "python3.13" / "site-packages" / "duckdb" / "__init__.py",
        project / "scheduler_app" / "__pycache__" / "db.cpython-313.pyc",
    ]
    watched = [
        project / "scheduler_app" / "main.py",
        project / "scheduler_app" / "db.py",
        LAUNCHER_DIR / "launcher.py",
    ]

    def excluded(path):
        return any(fnmatch(str(path), pattern)
                   for pattern in launcher.RELOADER_EXCLUDE_PATTERNS)

    for path in ignored:
        assert excluded(path), f"{path} should NOT trigger a reload"
    for path in watched:
        assert not excluded(path), f"{path} MUST still trigger a reload"
