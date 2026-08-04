"""
AIND Tool Launcher
Mounts multiple Flask apps at different URL paths on a single port.
"""

import sys
import os
import threading
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
from a2wsgi import ASGIMiddleware
from scheduler_app.main import create_app as create_scheduler_app

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
    """Build the scheduler WSGI app on the first request, not at import.

    Two reasons this must be lazy:
    - The werkzeug reloader (use_reloader=True) imports this module in BOTH
      the watcher process and the serving child; DuckDB is single-writer
      (file lock), so opening the database at import time in both processes
      would fail with "Could not set lock". Only the serving child handles
      requests, so lazy creation opens the DB exactly once, in the right
      process. create_app is reload-safe: schema creation is idempotent and
      auto-seeding only runs on an empty database.
    - DispatcherMiddleware strips the mount prefix out of PATH_INFO and into
      SCRIPT_NAME, but the scheduler's FastAPI routes are defined WITH the
      /session_schedule prefix (the app also runs standalone on :8000). The
      shim below re-prepends the prefix so the ASGI app sees the full path.
    """

    PREFIX = '/session_schedule'

    def __init__(self):
        self._app = None
        # run_simple below uses its default threaded=False, so requests are
        # sequential today — the lock is cheap insurance so first-request
        # creation stays single-shot if anyone ever flips threaded=True.
        self._lock = threading.Lock()

    def __call__(self, environ, start_response):
        if self._app is None:
            with self._lock:
                if self._app is None:
                    self._app = ASGIMiddleware(create_scheduler_app(db_path=SCHEDULER_DB))
        environ['PATH_INFO'] = self.PREFIX + environ.get('PATH_INFO', '')
        environ['SCRIPT_NAME'] = ''
        return self._app(environ, start_response)


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
        use_debugger=True
    )
