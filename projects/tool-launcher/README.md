# AIND Tool Launcher

A multi-tool Flask application launcher that mounts multiple tools at different URL paths on a single port.

## Purpose

This launcher allows you to run multiple Flask apps simultaneously on port 8080 (or any single port), making them all accessible through VPN at different URL paths:

- `http://your-vm-ip:8080/query_tool`
- `http://your-vm-ip:8080/fiber_schematic_viewer`
- `http://your-vm-ip:8080/session_schedule/` (Procedure Scheduler — a FastAPI/ASGI app, bridged in via `a2wsgi`, mounted fail-soft)
- (Future tools can be added easily)

## Setup

```bash
cd /home/doug.ollerenshaw/code/aind-workbench/projects/tool-launcher
uv sync
```

## Running

### One-time run:
```bash
uv run python launcher.py
```

### Persistent run (recommended for VM):
Use tmux to keep it running:

```bash
# Start a new tmux session
tmux new -s tools

# Run the launcher
cd /home/doug.ollerenshaw/code/aind-workbench/projects/tool-launcher
uv run python launcher.py

# Detach from tmux: Press Ctrl+B, then D
# To reattach later: tmux attach -t tools
```

## Adding New Tools

When you create a new tool in the future:

1. Create the new tool as a separate project in `projects/`
2. Edit `pyproject.toml`:
   - Add the new tool's dependencies to the `dependencies` list
   - Run `uv sync` to install them
3. Edit `launcher.py`:
   - Add the import path to `sys.path`
   - Import the app: `from new_tool import app as new_app`
   - Add to `DispatcherMiddleware`: `'/new_tool': new_app`
   - Add a link in the `index()` HTML

That's it! The launcher will automatically serve the new tool.

### A tool that runs as its own server

Some tools are separate projects with their own environment (the session tracker is one). Instead of importing them, the launcher forwards a path to their server on localhost: see `proxy_tool.py`, mounted at `/session_tracker`. The tool runs in its own tmux pane:

```bash
cd ~/code/session_tracker_prototype && uv run tracker --port 8765     # binds to 127.0.0.1; only the launcher reaches it
```

and is reachable at `http://your-vm-ip:8080/session_tracker/`. If the tracker is down, that address shows a short message saying how to start it. `SESSION_TRACKER_URL` overrides the forwarding address.

## Command-line Options

```bash
uv run python launcher.py --host 0.0.0.0 --port 8080
```

- `--host`: Host address to bind to (default: 0.0.0.0)
- `--port`: Port to bind to (default: 8080)

## Resilience: one broken tool cannot take down the others

**Incident, 2026-08-10.** `launcher.py` imported the procedure scheduler at
module scope (`from scheduler_app.main import create_app`). An edit in progress
left that package referencing an undefined name, the import raised at startup,
and the launcher process died — so **query_tool, fiber_schematic_viewer,
upgrader and iacuc_lookup were all offline because of an unrelated project's
half-finished file**. A second problem showed up in the same log: the reloader
watches every `.py` in each mounted project, so editing a *test* in
projects/procedure-scheduling restart-looped the live service.

Two fixes, both in `launcher.py`:

- **Fail-soft scheduler mount.** `LazySchedulerApp` now defers the *import* as
  well as the app creation, inside a guard. If importing or building the
  scheduler raises, `/session_schedule/` serves a plain-text **503** naming the
  exception (as text, never markup) and everything else keeps working. The
  failure is retried after `RETRY_AFTER_SECONDS` (30 s), so fixing the tree
  restores the mount without a restart, while a broken tree doesn't spin the
  log — it reports once per attempt, not once per request.
- **Scoped reloader.** `run_simple(..., exclude_patterns=RELOADER_EXCLUDE_PATTERNS)`
  ignores `tests/`, `test_*.py`, `conftest.py`, `.venv/`, `site-packages/`,
  `__pycache__/`, `*.pyc`, `data/`, `.cache/`, `.pytest_cache/`, `.git/`,
  `scratch/` and the scheduler's `client/`. Real source edits still trigger a
  reload; test and data churn no longer does.

### The rule this leaves behind

The launcher imports mounted tools **from the live working tree**, so an
unimportable tree is a production outage for every tool on the launcher. After
editing any mounted project's code, verify it still imports before moving on:

```bash
cd ../procedure-scheduling && uv run python -c "from scheduler_app.main import create_app"
```

`projects/procedure-scheduling/tests/test_imports.py` enforces this in pytest
(it walks every `scheduler_app` module), and
`projects/tool-launcher/tests/test_failsoft.py` asserts the blast radius stays
at one mount. Adding a new tool? Mount it the same fail-soft way rather than
importing it at module scope.

## Architecture

The launcher uses Werkzeug's `DispatcherMiddleware` to route requests:
- Root path (`/`) shows a landing page with links to all tools
- Each tool is mounted at its own path (e.g., `/query_tool`)
- All tools run in the same Python process
- Auto-reload is enabled for development
