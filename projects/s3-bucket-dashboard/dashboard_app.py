import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import sqlite3
import os
from aind_data_access_api.document_db import MetadataDbClient
import schedule
import time

# Configure page
st.set_page_config(
    page_title="Private S3 Bucket Dashboard", 
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database setup - specify full path relative to script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "dashboard_data.db")

def init_database():
    """Initialize SQLite database for historical tracking"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create table for historical snapshots
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bucket_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            project TEXT NOT NULL,
            asset_count INTEGER NOT NULL,
            UNIQUE(timestamp, project)
        )
    ''')
    
    # Create table for summary stats
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS snapshot_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL UNIQUE,
            total_private_assets INTEGER NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()

@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_current_data():
    """Fetch current data from AIND Document Database, focusing on private bucket only"""
    try:
        # Initialize the client
        client = MetadataDbClient(
            host="api.allenneuraldynamics.org",
            database="metadata_index",
            collection="data_assets",
        )
        
        # Pipeline that filters for private bucket only
        pipeline = [
            {
                '$match': {
                    'location': {'$regex': 'private', '$options': 'i'}  # Match locations containing 'private'
                }
            },
            {
                '$project': {
                    'project': '$data_description.project_name',
                    '_id': 0
                }
            }
        ]
        
        # Execute the aggregation
        results = client.aggregate_docdb_records(pipeline=pipeline)
        
        # Convert to DataFrame and group
        df = pd.DataFrame(results)
        if df.empty:
            return pd.DataFrame()
            
        grouped_df = df.groupby(['project']).size().reset_index(name='count')
        grouped_df = grouped_df.sort_values('count', ascending=False)
        
        return grouped_df
        
    except Exception as e:
        st.error(f"Error fetching data: {str(e)}")
        return pd.DataFrame()

def take_snapshot():
    """Fetch current data and save snapshot to database."""
    grouped_df = fetch_current_data()
    if grouped_df.empty:
        return

    conn = sqlite3.connect(DB_PATH)
    timestamp = datetime.now().isoformat()

    try:
        cursor = conn.cursor()

        # Save individual project counts
        for _, row in grouped_df.iterrows():
            cursor.execute('''
                INSERT OR REPLACE INTO bucket_snapshots 
                (timestamp, project, asset_count)
                VALUES (?, ?, ?)
            ''', (timestamp, row['project'], row['count']))

        # Calculate and save summary
        total_assets = grouped_df['count'].sum()

        cursor.execute('''
            INSERT OR REPLACE INTO snapshot_summaries 
            (timestamp, total_private_assets)
            VALUES (?, ?)
        ''', (timestamp, total_assets))

        conn.commit()
        st.success(f"Snapshot saved at {timestamp}")

    except Exception as e:
        st.error(f"Error saving snapshot: {str(e)}")
    finally:
        conn.close()

def load_historical_data():
    """Load historical data from database"""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame(), pd.DataFrame()
        
    conn = sqlite3.connect(DB_PATH)
    
    try:
        # Load summary data
        summary_df = pd.read_sql_query('''
            SELECT * FROM snapshot_summaries 
            ORDER BY timestamp
        ''', conn)
        
        # Load detailed project data
        project_df = pd.read_sql_query('''
            SELECT * FROM bucket_snapshots 
            ORDER BY timestamp, project
        ''', conn)
        
        if not summary_df.empty:
            summary_df['timestamp'] = pd.to_datetime(summary_df['timestamp'])
        if not project_df.empty:
            project_df['timestamp'] = pd.to_datetime(project_df['timestamp'])
            
        return summary_df, project_df
        
    except Exception as e:
        st.error(f"Error loading historical data: {str(e)}")
        return pd.DataFrame(), pd.DataFrame()
    finally:
        conn.close()

def display_metrics(grouped_df):
    """Display current metrics overview"""
    col1, col2 = st.columns(2)
    
    total_assets = grouped_df['count'].sum()
    project_count = len(grouped_df)
    
    col1.metric("Total Private Bucket Assets", f"{total_assets:,}")
    col2.metric("Projects with Private Assets", project_count)

def display_data_table(grouped_df):
    """Display the data table with re-indexing and percentage column"""
    st.subheader("Private Bucket Asset Count by Project")

    # Re-index the dataframe and add a percentage column
    total_count = grouped_df['count'].sum()
    grouped_df = grouped_df.sort_values('count', ascending=False).reset_index(drop=True)
    grouped_df['percentage'] = (grouped_df['count'] / total_count * 100).round(1)

    # Display the updated dataframe
    st.dataframe(grouped_df, use_container_width=True)

def create_pie_chart(grouped_df):
    """Create and display pie chart"""
    # Configurable chart parameters - adjust these values as needed
    PIE_CHART_HEIGHT = 600       # Overall height of the chart
    BOTTOM_MARGIN = 600          # Bottom margin for labels
    VERTICAL_SPACER_HEIGHT = 400  # Additional space after the chart
    
    fig_pie = px.pie(
        grouped_df, 
        values='count', 
        names='project',
        title="Private Bucket Distribution by Project"
    )
    
    # Calculate percentages for custom labels
    total_count = grouped_df['count'].sum()
    percentages = (grouped_df['count'] / total_count * 100).round(1)
    
    # Create custom labels with both count and percentage
    custom_labels = [f"{project}<br>{count:,} assets<br>{pct}%" 
                    for project, count, pct in zip(grouped_df['project'], grouped_df['count'], percentages)]
    
    # Update traces to show all projects with conditional label positioning
    fig_pie.update_traces(
        sort=False,  # Don't let plotly reorder
        textposition=['inside' if pct >= 10 else 'outside' for pct in percentages],
        textinfo='text',  # Use custom text
        text=custom_labels,
        hovertemplate='<b>%{label}</b><br>Count: %{value:,}<br>Percentage: %{percent}<extra></extra>'
    )
    
    # Adjust layout to prevent chart shrinking
    fig_pie.update_layout(
        autosize=False,  # Disable autosizing
        width=1000,  # Explicit width
        height=PIE_CHART_HEIGHT + BOTTOM_MARGIN,  # Combine height and margin
        margin=dict(l=50, r=50, t=80, b=BOTTOM_MARGIN),  # Explicit margins with adjustable bottom margin
        title=dict(
            text="Private Bucket Distribution by Project",
            x=0.5,  # Center the title
            font=dict(size=16)
        ),
        # Ensure labels don't get cut off
        annotations=[],  # Clear any existing annotations
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.05  # Position legend to the right
        )
    )
    
    # Add padding around the container
    st.markdown("<div style='padding: 20px;'>", unsafe_allow_html=True)
    st.plotly_chart(fig_pie, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Add configurable vertical spacer after the chart
    st.markdown(f"<div style='height: {VERTICAL_SPACER_HEIGHT}px;'></div>", unsafe_allow_html=True)

def display_trend_analysis(summary_df, project_df, grouped_df):
    """Display historical trend analysis with daily changes"""
    st.header("Historical Trends")

    if project_df.empty:
        st.info("No historical data available.")
        return

    # Filter for daily changes
    daily_changes_df = project_df.groupby(['timestamp', 'project']).sum().reset_index()

    st.subheader("Daily Changes by Project")
    st.dataframe(daily_changes_df, use_container_width=True)

    # Overall trend
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=summary_df['timestamp'], 
        y=summary_df['total_private_assets'],
        mode='lines+markers',
        name='Private Bucket Assets',
        line=dict(color='red')
    ))
    
    fig_trend.update_layout(
        title="Private Bucket Asset Count Trend",
        xaxis_title="Date",
        yaxis_title="Asset Count",
        hovermode='x unified',
        height=500
    )
    st.plotly_chart(fig_trend, use_container_width=True)
    
    # Change analysis
    if len(summary_df) > 1:
        latest = summary_df.iloc[-1]
        previous = summary_df.iloc[-2]
        
        total_change = latest['total_private_assets'] - previous['total_private_assets']
        
        st.metric(
            "Private Bucket Change", 
            f"{total_change:+,}",
            delta=f"{total_change:+,}" if total_change <= 0 else f"+{total_change:,}",
            delta_color="inverse"  # Red for increases, green for decreases
        )
    
    # Project trends over time
    if not project_df.empty:
        display_project_trends(project_df, grouped_df)

def display_project_trends(project_df, grouped_df):
    """Display project-level trends"""
    st.subheader("Project-level Trends")
    
    # Get top projects
    top_projects = grouped_df.nlargest(5, 'count')['project'].tolist()
    
    # Filter for just the top projects
    top_project_df = project_df[project_df['project'].isin(top_projects)]
    
    # Create pivot table with projects as columns
    pivot_df = top_project_df.pivot_table(
        values='asset_count', 
        index='timestamp',
        columns='project',
        fill_value=0
    )
    
    # Plot top projects
    fig_project_trends = go.Figure()
    
    for project in top_projects:
        if project in pivot_df.columns:
            fig_project_trends.add_trace(go.Scatter(
                x=pivot_df.index,
                y=pivot_df[project],
                mode='lines+markers',
                name=project
            ))
    
    fig_project_trends.update_layout(
        title="Top Projects in Private Bucket Over Time",
        xaxis_title="Date",
        yaxis_title="Asset Count",
        hovermode='x unified',
        height=500
    )
    st.plotly_chart(fig_project_trends, use_container_width=True)

def setup_sidebar(grouped_df):
    """Setup sidebar controls and return control states"""
    st.sidebar.header("Controls")
    
    auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", False)
    if auto_refresh:
        import time
        time.sleep(30)
        st.rerun()
    
    if st.sidebar.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()
        
    return auto_refresh

def display_sidebar_info(summary_df):
    """Display sidebar information"""
    st.sidebar.markdown("---")
    st.sidebar.info(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.sidebar.info(f"Database location: {DB_PATH}")
    
    if not summary_df.empty:
        last_snapshot = summary_df['timestamp'].max()
        st.sidebar.info(f"Last snapshot: {last_snapshot.strftime('%Y-%m-%d %H:%M:%S')}")

# Schedule the snapshot in the main function
def main():
    """Main dashboard function - orchestrates all components"""
    st.title("📊 Private S3 Bucket Dashboard")
    st.markdown("Track asset distribution across projects in the private S3 bucket")
    
    # Initialize database
    init_database()
    
    # Schedule daily snapshot at midnight
    schedule.every().day.at("00:00").do(take_snapshot)

    # Start the scheduler in a background thread
    import threading
    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(1)
    threading.Thread(target=run_scheduler, daemon=True).start()

    # Fetch current data
    st.header("Current Private Bucket Asset Distribution")
    
    with st.spinner("Fetching latest data..."):
        grouped_df = fetch_current_data()
    
    if grouped_df.empty:
        st.warning("No private bucket data available")
        return
    
    # Setup sidebar controls
    setup_sidebar(grouped_df)
    
    # Display current data
    display_metrics(grouped_df)
    display_data_table(grouped_df)
    create_pie_chart(grouped_df)
    
    # Load and display historical data
    summary_df, project_df = load_historical_data()
    display_trend_analysis(summary_df, project_df, grouped_df)
    
    # Display sidebar info
    display_sidebar_info(summary_df)

if __name__ == "__main__":
    main()