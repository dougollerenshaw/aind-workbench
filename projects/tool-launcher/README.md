# AIND Tool Launcher

A multi-tool Flask application launcher that mounts multiple tools at different URL paths on a single port.

## Purpose

This launcher allows you to run multiple Flask apps simultaneously on port 8080 (or any single port), making them all accessible through VPN at different URL paths:

- `http://your-vm-ip:8080/query_tool`
- `http://your-vm-ip:8080/fiber_schematic_viewer`
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

## Command-line Options

```bash
uv run python launcher.py --host 0.0.0.0 --port 8080
```

- `--host`: Host address to bind to (default: 0.0.0.0)
- `--port`: Port to bind to (default: 8080)

## Architecture

The launcher uses Werkzeug's `DispatcherMiddleware` to route requests:
- Root path (`/`) shows a landing page with links to all tools
- Each tool is mounted at its own path (e.g., `/query_tool`)
- All tools run in the same Python process
- Auto-reload is enabled for development
