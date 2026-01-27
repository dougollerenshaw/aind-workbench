# AIND Metadata Upgrader Tool

A Flask web application for testing whether AIND metadata assets can successfully upgrade from schema v1 to v2.

## Features

- Search by asset ID or name
- Test upgrade compatibility
- View detailed error messages if upgrade fails
- See which metadata files were upgraded
- Full error traceback for debugging

## Usage

### Standalone

```bash
uv run python upgrader_app.py
```

Then visit http://localhost:5001

### Via Tool Launcher

The app is integrated into the AIND tool launcher. Run:

```bash
cd ../tool-launcher
uv run python launcher.py
```

Then visit http://localhost:8080/upgrader

## How It Works

1. Enter an asset ID (UUID) or asset name
2. The tool fetches the asset from DocDB v1
3. Attempts to run the metadata upgrader
4. Shows success/failure with detailed information

## Development

The app uses:
- Flask for the web framework
- aind-data-access-api for DocDB access
- aind-metadata-upgrader for upgrade logic

## Testing

Test with known assets:
- **Broken asset:** `733a1052-683c-46d2-96ca-8f89bd270192` (fails on fiber channel data)
- **Working asset:** Search for a recent asset to test successful upgrades
