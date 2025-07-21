#!/usr/bin/env python3
"""
Simple script to aggregate reward volume data using existing make_acquisitions.py logic.
"""

import os
import pandas as pd
from datetime import datetime
import zoneinfo
from pathlib import Path

# Import the key functions from make_acquisitions.py
from make_acquisitions import session_path_exists, create_session_datetime
from utils import load_session_data, extract_behavioral_metrics
from metadata_utils import get_session_details, get_mapped_subject_id

def main():
    """Create a summary CSV of reward volume data."""
    
    # Load asset inventory
    inventory_path = "asset_inventory.csv"
    print(f"Loading asset inventory from: {os.path.abspath(inventory_path)}")
    inventory_df = pd.read_csv(inventory_path)
    print(f"Loaded {len(inventory_df)} sessions from asset inventory")
    
    results = []
    
    print("Analyzing reward volumes...")
    
    for idx, row in inventory_df.iterrows():
        session_name = row["session_name"]
        
        # Skip if missing required fields (same logic as make_acquisitions.py)
        if pd.isna(row["subject_id"]) or pd.isna(row["collection_date"]) or pd.isna(row["vast_path"]):
            continue
            
        # Check if session path exists (same logic as make_acquisitions.py)
        if not session_path_exists(row["vast_path"], session_name):
            continue
        
        print(f"  Processing {session_name}...")
        
        try:
            # Get mapped subject ID (same as make_acquisitions.py)
            subject_id = get_mapped_subject_id(row["subject_id"])
            
            # Create session datetime to get proper date for spreadsheet lookup
            acquisition_start_time = create_session_datetime(
                row["collection_date"], 
                row["vast_path"], 
                session_name, 
                row["collection_site"]
            )
            session_date = acquisition_start_time.strftime('%Y-%m-%d')
            
            # Get session details (same as make_acquisitions.py)
            session_details = get_session_details(subject_id, session_date)
            
            # Load behavioral data (same as make_acquisitions.py)
            mat_path = os.path.join(row["vast_path"], "sorted", "session", f"{session_name}_sessionData_behav.mat")
            beh_df, licks_L, licks_R = load_session_data(mat_path)
            
            # Extract behavioral metrics (same as make_acquisitions.py)
            reward_size = session_details.get('reward_size', 3.0) if session_details else 3.0
            expected_water = session_details.get('water_received') if session_details else None
            
            metrics = extract_behavioral_metrics(
                beh_df, 
                licks_L, 
                licks_R, 
                volume_per_reward=reward_size, 
                expected_water_received=expected_water
            )
            
            # Calculate comparison metrics
            spreadsheet_reward_size = session_details.get('reward_size') if session_details else None
            
            # Get reward counts from separate left and right fields
            spreadsheet_reward_count = None
            if session_details:
                left_rewards = session_details.get('num_reward_left', 0) or 0
                right_rewards = session_details.get('num_reward_right', 0) or 0
                if left_rewards or right_rewards:  # If either is non-zero
                    spreadsheet_reward_count = left_rewards + right_rewards
            
            spreadsheet_calculated_volume = spreadsheet_reward_size * spreadsheet_reward_count if (spreadsheet_reward_size and spreadsheet_reward_count) else None
            spreadsheet_water_received_ul = session_details.get('water_received') * 1000 if session_details and session_details.get('water_received') else None
            
            # Boolean check: does spreadsheet water received match calculated volume?
            volumes_match = False
            if spreadsheet_water_received_ul and spreadsheet_calculated_volume:
                # Allow for small rounding differences (within 1 microliter)
                volumes_match = abs(spreadsheet_water_received_ul - spreadsheet_calculated_volume) <= 1
            
            # Behavioral data
            behavioral_reward_count = metrics['total_rewards']
            behavioral_water_volume_ul = metrics['reward_volume_microliters']
            
            # Calculate percentage difference between behavioral and spreadsheet volumes
            volume_diff_percent = None
            if spreadsheet_water_received_ul and behavioral_water_volume_ul and spreadsheet_water_received_ul > 0:
                volume_diff_percent = ((behavioral_water_volume_ul - spreadsheet_water_received_ul) / spreadsheet_water_received_ul) * 100
            
            # Compile results
            result = {
                'session_name': session_name,
                'subject_id': subject_id,
                'session_date': session_date,
                'spreadsheet_reward_size_ul': spreadsheet_reward_size,
                'spreadsheet_reward_count_total': spreadsheet_reward_count,
                'spreadsheet_calculated_volume_ul': spreadsheet_calculated_volume,
                'spreadsheet_water_received_ul': spreadsheet_water_received_ul,
                'volumes_match_spreadsheet': volumes_match,
                'behavioral_reward_count': behavioral_reward_count,
                'behavioral_water_volume_ul': behavioral_water_volume_ul,
                'percent_diff_behavioral_vs_spreadsheet': round(volume_diff_percent, 1) if volume_diff_percent is not None else None,
            }
            
            results.append(result)
            
        except Exception as e:
            print(f"  Error processing {session_name}: {e}")
            continue
    
    if not results:
        print("No sessions were successfully analyzed.")
        return
    
    # Create DataFrame and save to CSV
    results_df = pd.DataFrame(results)
    output_path = "reward_volume_analysis.csv"
    results_df.to_csv(output_path, index=False)
    
    print(f"\nAnalysis complete!")
    print(f"Results saved to: {output_path}")
    print(f"Analyzed {len(results)} sessions")
    
    # Show summary statistics
    print(f"\nSummary:")
    print(f"Sessions with spreadsheet data: {results_df['spreadsheet_reward_size_ul'].notna().sum()}")
    print(f"Sessions with behavioral data: {results_df['behavioral_reward_count'].notna().sum()}")
    print(f"Sessions where spreadsheet volumes match: {results_df['volumes_match_spreadsheet'].sum()}")
    
    # Show sessions with large percentage differences
    large_diffs = results_df[results_df['percent_diff_behavioral_vs_spreadsheet'].notna() & 
                            (results_df['percent_diff_behavioral_vs_spreadsheet'].abs() > 10)]
    if len(large_diffs) > 0:
        print(f"Sessions with >10% volume difference: {len(large_diffs)}")
        print(f"\nTop 5 largest differences:")
        # Sort by absolute value of percentage difference
        large_diffs_sorted = large_diffs.assign(
            abs_percent_diff=large_diffs['percent_diff_behavioral_vs_spreadsheet'].abs()
        ).nlargest(5, 'abs_percent_diff')
        
        top_diffs = large_diffs_sorted[
            ['session_name', 'spreadsheet_water_received_ul', 'behavioral_water_volume_ul', 'percent_diff_behavioral_vs_spreadsheet']
        ]
        print(top_diffs.to_string(index=False))

if __name__ == "__main__":
    main()
