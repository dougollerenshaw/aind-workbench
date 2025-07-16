# S3 Bucket Asset Dashboard

This dashboard provides a streamlined way to monitor and analyze asset distribution across S3 buckets and projects. It includes tools for tracking historical changes and visualizing trends.

## Features

- **Real-time Data**: Fetches current asset counts from the AIND Document Database.
- **Historical Tracking**: Stores snapshots in a local SQLite database to monitor changes over time.
- **Visual Analytics**: Interactive charts and tables for asset distribution and project-level breakdowns.
- **Automated Monitoring**: Daily snapshots are taken automatically to ensure up-to-date tracking.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the dashboard:
   ```bash
   streamlit run dashboard_app.py
   ```

3. Open your browser to the displayed URL (typically `http://localhost:8501`).

## Usage

### Monitoring
- The dashboard automatically refreshes daily snapshots at midnight.
- Use the interactive charts and tables to explore asset distribution and trends.

### Deployment
- Run the app on your VM with:
  ```bash
  streamlit run dashboard_app.py
  ```

## Data Sources

- **Current Data**: Pulled from the AIND Document Database (`api.allenneuraldynamics.org`).
- **Historical Data**: Stored locally in `dashboard_data.db`.
