"""
AIND Tool Launcher
Mounts multiple Flask apps at different URL paths on a single port.
"""

import sys
import os
import threading
import time
import traceback
from pathlib import Path
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple
from flask import Flask

# Get the projects directory
PROJECTS_DIR = Path(__file__).parent.parent
# Repo root, so the shared `aind_workbench` package is importable.
REPO_ROOT = PROJECTS_DIR.parent

# Add tool directories to path
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(PROJECTS_DIR / 'query_tool'))
sys.path.insert(0, str(PROJECTS_DIR / 'fiber-schematic-viewer'))
sys.path.insert(0, str(PROJECTS_DIR / 'upgrader-tool'))
sys.path.insert(0, str(PROJECTS_DIR / 'iacuc_lookup_api'))
# procedure-scheduling is APPENDED, not inserted at the front: it has its own
# top-level app.py (standalone CLI entry), which must never shadow
# fiber-schematic-viewer's `app` module imported below. Its package is named
# `scheduler_app` precisely to avoid that collision.
sys.path.append(str(PROJECTS_DIR / 'procedure-scheduling'))

# Import the Flask apps from each tool
from query_tool import app as query_app
from app import app as fiber_app
from upgrader_app import app as upgrader_app
from iacuc_app import app as iacuc_app

# The procedure scheduler is a FastAPI (ASGI) app; a2wsgi bridges it into
# this WSGI dispatcher.
#
# NOTE: `scheduler_app` is deliberately NOT imported here. It used to be, and on
# 2026-08-10 a half-finished edit left that package referencing an undefined
# name — the module-scope import raised at startup and took the WHOLE launcher
# down, so query_tool, fiber_schematic_viewer, upgrader and iacuc_lookup were
# all offline because of an unrelated project's broken file. The import now
# happens inside LazySchedulerApp, guarded, so a broken scheduler can only ever
# break /session_schedule. See the tool-launcher README.
from a2wsgi import ASGIMiddleware

# Configure apps to know their mount points
query_app.config['APPLICATION_ROOT'] = '/query_tool'
fiber_app.config['APPLICATION_ROOT'] = '/fiber_schematic_viewer'
upgrader_app.config['APPLICATION_ROOT'] = '/upgrader'
iacuc_app.config['APPLICATION_ROOT'] = '/iacuc_lookup'

# Configure fiber app cache directory (absolute path)
fiber_app.config['CACHE_DIR'] = str(PROJECTS_DIR / 'fiber-schematic-viewer' / '.cache' / 'procedures')

# Absolute DB path so the launcher's cwd doesn't matter. Overridable via the
# SCHEDULER_DB env var so tests (or a staging run) can point the scheduler at
# a throwaway database instead of the real one.
SCHEDULER_DB = Path(os.environ.get(
    'SCHEDULER_DB',
    str(PROJECTS_DIR / 'procedure-scheduling' / 'data' / 'procedure_scheduling.duckdb'),
))


class LazySchedulerApp:
    """Import and build the scheduler on first request, and FAIL SOFT.

    Three reasons this is lazy and guarded:

    - **Blast radius.** The scheduler lives in a working tree that people edit.
      If importing or building it raises, only this mount may break: the other
      four tools must keep serving. Deferring the *import* (not just the app
      creation) is the whole point — a module-scope import of a
      half-finished package is what took the launcher down on 2026-08-10.
    - **DuckDB is single-writer.** The werkzeug reloader imports this module in
      both the watcher and the serving child; opening the database in both
      would fail with "Could not set lock". Only the serving child handles
      requests, so first-request creation opens it exactly once, in the right
      process. create_app is reload-safe (idempotent schema, auto-seed only
      when empty).
    - **Prefix.** DispatcherMiddleware strips the mount prefix into
      SCRIPT_NAME, but the scheduler's FastAPI routes are defined WITH the
      /session_schedule prefix (it also runs standalone on :8000), so the shim
      re-prepends it.
    """

    PREFIX = '/session_schedule'
    # After a failure, wait this long before trying to import again. Long
    # enough that a broken tree doesn't spin the log on every page refresh,
    # short enough that a fix is picked up without a restart.
    RETRY_AFTER_SECONDS = 30

    def __init__(self):
        self._app = None
        # run_simple below uses its default threaded=False, so requests are
        # sequential today — the lock is cheap insurance so first-request
        # creation stays single-shot if anyone ever flips threaded=True.
        self._lock = threading.Lock()
        self._error = None          # (message, monotonic timestamp)

    def _build(self):
        """Import and construct the scheduler. Raises on a broken tree."""
        from scheduler_app.main import create_app as create_scheduler_app

        return ASGIMiddleware(create_scheduler_app(db_path=SCHEDULER_DB))

    def _ensure_app(self):
        """The built app, or None if it is currently unavailable."""
        if self._app is not None:
            return self._app
        with self._lock:
            if self._app is not None:
                return self._app
            if self._error is not None:
                _, failed_at = self._error
                if time.monotonic() - failed_at < self.RETRY_AFTER_SECONDS:
                    return None          # still in the backoff window
            try:
                self._app = self._build()
            except Exception as exc:
                # Log once per attempt (not per request) and keep serving the
                # other tools. A later request retries after the backoff.
                self._error = (f"{type(exc).__name__}: {exc}", time.monotonic())
                print(
                    f"[launcher] scheduler unavailable: {self._error[0]} "
                    f"(retrying in {self.RETRY_AFTER_SECONDS}s; other tools unaffected)",
                    file=sys.stderr,
                )
                traceback.print_exc()
                return None
            self._error = None
            return self._app

    def _serve_error(self, environ, start_response):
        """Plain-text 503 so a broken scheduler is obvious but contained.

        text/plain, not HTML: the exception text is data and must never be
        rendered as markup.
        """
        message, failed_at = self._error or ('not initialised', time.monotonic())
        retry_in = max(0, int(self.RETRY_AFTER_SECONDS - (time.monotonic() - failed_at)))
        body = (
            "Procedure Scheduler unavailable\n"
            "===============================\n\n"
            f"The scheduler app could not be loaded:\n\n    {message}\n\n"
            f"The launcher will retry in about {retry_in}s, so a fix is picked "
            "up without restarting.\n"
            "The other tools on this launcher are unaffected — see / for the list.\n\n"
            "Usual cause: an edit in progress left projects/procedure-scheduling "
            "unimportable.\nCheck with:\n\n"
            "    cd projects/procedure-scheduling && "
            "uv run python -c 'from scheduler_app.main import create_app'\n"
        ).encode()
        start_response('503 Service Unavailable', [
            ('Content-Type', 'text/plain; charset=utf-8'),
            ('Content-Length', str(len(body))),
            ('Retry-After', str(self.RETRY_AFTER_SECONDS)),
            ('Cache-Control', 'no-store'),
        ])
        return [body]

    def __call__(self, environ, start_response):
        app = self._ensure_app()
        if app is None:
            return self._serve_error(environ, start_response)
        environ['PATH_INFO'] = self.PREFIX + environ.get('PATH_INFO', '')
        environ['SCRIPT_NAME'] = ''
        return app(environ, start_response)


scheduler_app_wsgi = LazySchedulerApp()

# Create a simple root app with tool directory
root_app = Flask(__name__)

@root_app.route('/')
def index():
    """Simple landing page with links to all available tools."""
    return '''
    <h1>AIND Tools</h1>
    <ul>
        <li><a href="/query_tool">Query Tool</a> - Query DocDB metadata</li>
        <li><a href="/fiber_schematic_viewer">Fiber Schematic Viewer</a> - Visualize fiber implants</li>
        <li><a href="/upgrader">Metadata Upgrader</a> - Test asset metadata upgrade from v1 to v2</li>
        <li><a href="/iacuc_lookup">IACUC Lookup</a> - Look up the IACUC protocol for a mouse (form + JSON API)</li>
        <li><a href="/session_schedule">Procedure Scheduler</a> - Schedule acquisition sessions (calendar + API)</li>
    </ul>
    '''

# Mount apps at different paths
application = DispatcherMiddleware(root_app, {
    '/query_tool': query_app,
    '/fiber_schematic_viewer': fiber_app,
    '/upgrader': upgrader_app,
    '/iacuc_lookup': iacuc_app,
    '/session_schedule': scheduler_app_wsgi,
})

# The reloader watches every file belonging to an imported module, which means
# a whole project's tree — so editing a test in projects/procedure-scheduling
# restart-looped this live service. Keep the reloader (Doug relies on it for
# real code changes) but stop non-code and test-only edits from triggering it.
# Patterns are fnmatch-style, matched against absolute file paths.
RELOADER_EXCLUDE_PATTERNS = [
    '*/tests/*',              # test edits are not deployments
    '*/test_*.py',
    '*/conftest.py',
    '*/.venv/*',              # dependency trees
    '*/site-packages/*',
    '*/__pycache__/*',
    '*.pyc',
    '*/data/*',               # DuckDB files and Parquet exports
    '*/.pytest_cache/*',
    '*/.cache/*',             # fiber viewer's procedure cache
    '*/.git/*',
    '*/scratch/*',
    '*/client/*',             # the scheduler's client package is not served here
]


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='AIND Tool Launcher')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                        help='Host address to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8080,
                        help='Port to bind to (default: 8080)')

    args = parser.parse_args()

    print(f"Starting AIND Tool Launcher on {args.host}:{args.port}")
    print(f"Available tools:")
    print(f"  - Query Tool: http://localhost:{args.port}/query_tool")
    print(f"  - Fiber Schematic Viewer: http://localhost:{args.port}/fiber_schematic_viewer")
    print(f"  - Metadata Upgrader: http://localhost:{args.port}/upgrader")
    print(f"  - IACUC Lookup (REST): http://localhost:{args.port}/iacuc_lookup?subject_id=762287")
    print(f"  - Procedure Scheduler: http://localhost:{args.port}/session_schedule/")
    print(f"Fiber Schematic Viewer cache directory: {fiber_app.config['CACHE_DIR']}")

    run_simple(
        args.host,
        args.port,
        application,
        use_reloader=True,
        use_debugger=True,
        exclude_patterns=RELOADER_EXCLUDE_PATTERNS,
    )
