# Fiber Schematic Viewer

Automated generation of fiber implant location schematics from AIND metadata.

## Setup

```bash
# Install dependencies with uv
uv pip install -e .

# Or install directly
uv pip install flask matplotlib numpy
```

## Running

```bash
# Start the Flask app on port 8081
python app.py

# With custom cache settings
python app.py --cache-dir /path/to/cache --cache-ttl 72
```

Then visit: `http://your-vm-ip:8081`

Options:
- `--cache-dir`: Cache directory path (default: `.cache/procedures`)
- `--cache-ttl`: Cache time-to-live in hours (default: 168 = 1 week)

## Usage

1. Enter a mouse subject ID (e.g., "775741")
2. Press Enter or click "Generate Schematic"
3. View the automatically generated fiber implant schematic
4. Download or print the high-resolution PNG

## How it works

- Queries AIND Metadata Service for subject procedures from source systems
- **Caches results locally** for fast repeated access
- Extracts fiber implant coordinates (AP, ML, DV, angles)
- Generates anatomical skull diagram with fiber locations
- All colors and visual parameters are configurable in `config.py`

**Performance**: 
- First query: ~30-40 seconds (metadata service)
- Cached queries: < 0.1 seconds
- Cache TTL: 1 week (configurable)

## Customization

Edit `config.py` to change:
- Fiber marker colors
- Skull dimensions
- Bregma/Lambda marker colors
- Font sizes and styles