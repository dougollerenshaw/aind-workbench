"""
Analyze patterns in the affected assets
"""

import pandas as pd
from datetime import datetime


def analyze_patterns():
    """Analyze patterns in affected assets"""
    df = pd.read_csv("affected_assets.csv")
    
    # Convert created to datetime (handle mixed formats and timezones)
    df["created"] = pd.to_datetime(df["created"], format="mixed", utc=True)
    df["created_date"] = df["created"].dt.date
    df["created_month"] = df["created"].dt.to_period("M")
    
    print("=== Pattern Analysis ===\n")
    
    # 1. Distribution by number of fiber connections
    print("Distribution by number of fiber connections:")
    fc_dist = df.groupby("num_fiber_connections").agg({
        "_id": "count",
        "missing_channel_data": "sum"
    }).rename(columns={"_id": "total_assets", "missing_channel_data": "missing_channel"})
    fc_dist["percent_missing"] = (fc_dist["missing_channel"] / fc_dist["total_assets"] * 100).round(1)
    print(fc_dist)
    print()
    
    # 2. Timeline of affected assets
    print("Assets by month:")
    monthly = df.groupby("created_month").agg({
        "_id": "count",
        "missing_channel_data": "sum"
    }).rename(columns={"_id": "total", "missing_channel_data": "missing"})
    print(monthly.tail(15))
    print()
    
    # 3. Session version breakdown
    print("Session version breakdown:")
    version_dist = df.groupby("session_version").agg({
        "_id": "count",
        "missing_channel_data": "sum"
    }).rename(columns={"_id": "total", "missing_channel_data": "missing"})
    print(version_dist)
    print()
    
    # 4. First and last occurrence
    print("Timeline:")
    print(f"Earliest asset created: {df['created'].min()}")
    print(f"Latest asset created: {df['created'].max()}")
    print()
    
    print("Earliest asset with missing channel data:")
    missing_df = df[df["missing_channel_data"] == True]
    earliest = missing_df.nsmallest(1, "created").iloc[0]
    print(f"  {earliest['_id']}")
    print(f"  Name: {earliest['name']}")
    print(f"  Created: {earliest['created']}")
    print(f"  Session: {earliest['session_version']}")
    print()
    
    print("Latest asset with missing channel data:")
    latest = missing_df.nlargest(1, "created").iloc[0]
    print(f"  {latest['_id']}")
    print(f"  Name: {latest['name']}")
    print(f"  Created: {latest['created']}")
    print(f"  Session: {latest['session_version']}")
    print()
    
    # 5. Assets that DO have channel data
    has_channel = df[df["missing_channel_data"] == False]
    print(f"Assets WITH channel data: {len(has_channel)}")
    if len(has_channel) > 0:
        print("Examples of assets with proper channel data:")
        for _, row in has_channel.head(5).iterrows():
            print(f"  {row['_id']}: {row['name']} ({row['num_fiber_connections']} connections)")


if __name__ == "__main__":
    analyze_patterns()
