"""
AIND Tool Launcher
Mounts multiple Flask apps at different URL paths on a single port.
"""

import sys
import os
from pathlib import Path
import importlib.util
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple
from flask import Flask

# Get the projects directory
PROJECTS_DIR = Path(__file__).parent.parent


def load_app_from_file(file_path, app_name='app'):
    """Load a Flask app from a Python file"""
    spec = importlib.util.spec_from_file_location(f"module_{file_path.stem}", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, app_name)


# Load Flask apps
sys.path.insert(0, str(PROJECTS_DIR / 'query_tool'))
from query_tool import app as query_app

fiber_app = load_app_from_file(PROJECTS_DIR / 'fiber-schematic-viewer' / 'app.py')
upgrader_app = load_app_from_file(PROJECTS_DIR / 'upgrader-tool' / 'app.py')

# Configure apps to know their mount points
query_app.config['APPLICATION_ROOT'] = '/query_tool'
fiber_app.config['APPLICATION_ROOT'] = '/fiber_schematic_viewer'
upgrader_app.config['APPLICATION_ROOT'] = '/upgrader'

# Configure fiber app cache directory (absolute path)
fiber_app.config['CACHE_DIR'] = str(PROJECTS_DIR / 'fiber-schematic-viewer' / '.cache' / 'procedures')

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
    </ul>
    '''

# Mount apps at different paths
application = DispatcherMiddleware(root_app, {
    '/query_tool': query_app,
    '/fiber_schematic_viewer': fiber_app,
    '/upgrader': upgrader_app,
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
    print(f"Fiber Schematic Viewer cache directory: {fiber_app.config['CACHE_DIR']}")
    
    run_simple(
        args.host, 
        args.port, 
        application, 
        use_reloader=True, 
        use_debugger=True
    )
