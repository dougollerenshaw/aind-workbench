# S3 Bucket Asset Dashboard

A Streamlit dashboard to track and visualize asset distribution across S3 buckets and projects, with historical trend analysis.

## Features

- **Real-time Data**: Fetches current asset counts from AIND Document Database
- **Historical Tracking**: SQLite database stores snapshots to track changes over time
- **Visual Analytics**: 
  - Interactive charts showing bucket distributions
  - Trend analysis for private bucket asset reduction
  - Project-level breakdowns
- **Easy Monitoring**: Auto-refresh and manual snapshot capabilities

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the dashboard:
```bash
streamlit run dashboard_app.py
```

3. Open your browser to the displayed URL (typically `http://localhost:8501`)

## Usage

### First Time Setup
1. Click "Save Snapshot" to capture your first data point
2. Set up regular snapshots (manually or via cron) to track trends

### Monitoring
- Use "Auto-refresh" for live monitoring
- Click "Refresh Data" to get latest counts
- Historical trends show progress in reducing private bucket assets

### Deployment
- Run on your VM with: `streamlit run dashboard_app.py --port 8080`
- Ask IT to map a clean URL to `your-vm-ip:8080`
- No "streamlit" will appear in the final URL

## Data Sources

- **Current Data**: AIND Document Database (`api.allenneuraldynamics.org`)
- **Historical Data**: Local SQLite database (`dashboard_data.db`)

## Key Metrics

- **Total Assets**: All assets across all buckets
- **Private Bucket Assets**: Assets that need to be moved (highlighted in red)
- **Trend Analysis**: Shows progress over time (decreases = good progress)