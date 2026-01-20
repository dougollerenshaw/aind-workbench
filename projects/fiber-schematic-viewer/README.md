# Fiber Schematic Viewer

Web app that generates fiber implant location schematics from AIND metadata.

## Setup

```bash
uv pip install -e .
```

## Running

```bash
# Start on port 8081
python app.py

# Custom port/cache
python app.py --port 8080 --cache-dir /path/to/cache
```

Then visit `http://your-vm-ip:8081`

## How to Use

1. Enter a mouse subject ID (e.g., "775741")
2. Click "Generate Schematic"
3. View/download the fiber implant diagram

## How It Works

Queries the AIND Metadata Service for procedures data, extracts fiber coordinates, and generates a top-down skull schematic showing implant locations.

**Performance:**
- First query: ~30-40 seconds
- Repeat queries: < 0.1 seconds (cached)

## Cache

Results are cached at `.cache/procedures/` as JSON files (one per subject). Cache never expires.

To refresh data for a subject:
```bash
rm .cache/procedures/<subject_id>.json
```

## Customization

Edit `config.py` to change colors, fonts, or dimensions.

## Files

- `app.py` - Main Flask application
- `config.py` - Visual configuration
- `params/templates/index.html` - Frontend
- `params/static/style.css` - Styles
