# AIND MongoDB Query Tool

A simple web interface for running MongoDB aggregation queries against the AIND metadata database.

## Setup (uv)

1. Create and activate a virtual environment with [uv](https://docs.astral.sh/uv/):
```bash
uv venv
source .venv/bin/activate
```

2. Install dependencies from `pyproject.toml`:
```bash
uv sync
```

3. Run the app:
```bash
uv run python query_tool.py
```

4. Open your browser to: `http://localhost:5000`

### Command-line options:
```bash
uv run python query_tool.py --host 0.0.0.0 --port 5000 --default_limit 100
```

- `--host`: Host address to bind to (default: `0.0.0.0`)
- `--port`: Port to bind to (default: `5000`)
- `--default_limit`: Default limit for single document queries (default: `100`)
- `--prod_host`: MongoDB production host (default: `api.allenneuraldynamics.org`)
- `--dev_host`: MongoDB development host (default: `api.allenneuraldynamics-test.org`)

## Remote access from your Mac (VM running the app)

1. On the VM, run the app bound to all interfaces (default):
```bash
cd projects/query_tool
uv run python query_tool.py
```
(Internally this uses `host=0.0.0.0` and `port=5000`.)

2. Find the VM's IP on the VPN network:
```bash
hostname -I
```
Pick the VPN-reachable address (often `10.x.x.x`).

3. From your Mac, open: `http://<VM_IP>:5000`

4. If the page does not load, check:
- VM firewall allows inbound TCP 5000.
- VPN routing allows direct access to the VM IP.
- No other process is using port 5000.

### Custom host/port (optional)
You can override host/port when launching:
```bash
uv run python query_tool.py --port 8080
```
Then browse to `http://<VM_IP>:8080`.

## Input format tips
- Accepts standard JSON arrays (aggregation pipelines).
- Also accepts single JSON objects (treated as `{"$match": obj}` with an automatic limit).
- Relaxed JSON is supported (via JSON5): unquoted keys like `_id`, single quotes, and trailing commas are allowed for quick copy/paste from Mongo-style queries.

## Usage

- Select the database environment (Production/Development) and version (V1/V2) using the radio buttons
- Paste a MongoDB aggregation pipeline (as a JSON array) into the text box
- Click "Run Query" or press Enter
- View results in Tree or JSON format

## Example Queries

### Count assets by project:
```json
[
  {"$group": {"_id": "$data_description.project_name", "count": {"$sum": 1}}},
  {"$sort": {"count": -1}},
  {"$limit": 10}
]
```

### Find assets for a specific subject:
```json
[
  {"$match": {"subject.subject_id": "123456"}},
  {"$project": {"_id": 1, "location": 1, "created": 1}},
  {"$limit": 10}
]
```

### Bucket distribution for a project:
```json
[
  {"$match": {"data_description.project_name": "Cognitive flexibility in patch foraging"}},
  {"$project": {"bucket": {"$arrayElemAt": [{"$split": ["$location", "/"]}, 2]}, "created": 1}},
  {"$group": {"_id": "$bucket", "count": {"$sum": 1}, "first_date": {"$min": "$created"}, "last_date": {"$max": "$created"}}},
  {"$sort": {"first_date": 1}}
]
```

## Deployment on VM

To make this accessible from other machines on your network:

1. The app is already configured to run on `0.0.0.0:5000`
2. Make sure port 5000 is open on your VM's firewall
3. Access it from other machines at: `http://YOUR_VM_IP:5000`

For production use, consider:
- Using a production WSGI server like gunicorn instead of Flask's dev server
- Setting up nginx as a reverse proxy
- Adding authentication if needed