# Test Upgrader

Test script for debugging AIND metadata upgrader issues.

## Setup with uv

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Run the script:
   ```bash
   uv run python 2025.12.23_test_upgrader.py
   ```

Or activate the virtual environment:
```bash
source .venv/bin/activate  # On macOS/Linux
python 2025.12.23_test_upgrader.py
```

## Dependencies

- `aind-data-access-api` - For accessing the metadata database
- `aind-metadata-upgrader` - For upgrading metadata schemas
