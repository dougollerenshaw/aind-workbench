#!/usr/bin/env python3
"""
Extract all goals from the Excel spreadsheet and create a complete JSON file.
"""

import pandas as pd
import json
import re


def extract_all_goals():
    """Extract all goals from the Excel file"""

    # Read the Excel file
    df = pd.read_excel("SciComp GoalsResourcing Summary.xlsx")

    goals = []
    current_platform = None
    current_lead = None

    # Column mapping based on the structure we observed
    # Column 0: Platform (or empty for sub-goals)
    # Column 1: Lead (or empty for sub-goals)
    # Column 2: Planning Doc Link
    # Column 3: Goal Title
    # Column 4: Priority
    # Column 5: Size
    # Column 6: Status
    # Column 7: Description
    # Column 8: Success Criteria
    # Column 9: Risks
    # Column 38: Resource Summary

    for i in range(len(df)):
        row = df.iloc[i]

        # Check if this is a platform header
        platform = row.iloc[0] if pd.notna(row.iloc[0]) else None
        lead = row.iloc[1] if pd.notna(row.iloc[1]) else None
        title = row.iloc[3] if pd.notna(row.iloc[3]) else None

        # Convert empty strings to None for cleaner logic
        if platform == "":
            platform = None
        if lead == "":
            lead = None
        if title == "":
            title = None

        # If this row has both platform and title, it's a goal (not a platform header)
        if (
            platform
            and title
            and platform != "Project/platform"
            and platform != "OVERALL RESOURCING TOTALS"
        ):
            # This is a goal row with platform info - also set current platform for subsequent goals
            current_platform = platform
            current_lead = lead

            priority = row.iloc[4] if pd.notna(row.iloc[4]) else None
            size = row.iloc[5] if pd.notna(row.iloc[5]) else None
            status = row.iloc[6] if pd.notna(row.iloc[6]) else None
            description = row.iloc[7] if pd.notna(row.iloc[7]) else None
            success_criteria = row.iloc[8] if pd.notna(row.iloc[8]) else None
            risks = row.iloc[9] if pd.notna(row.iloc[9]) else None
            resource_summary = row.iloc[38] if pd.notna(row.iloc[38]) else None

            goal = {
                "platform": platform,
                "lead": lead,
                "title": str(title).strip(),
                "priority": str(priority).strip() if priority else None,
                "size": str(size).strip() if size else None,
                "description": (
                    str(description).strip() if description else None
                ),
                "status": str(status).strip() if status else None,
                "success_criteria": (
                    str(success_criteria).strip() if success_criteria else None
                ),
                "risks": str(risks).strip() if risks else None,
                "resource_summary": (
                    str(resource_summary).strip() if resource_summary else None
                ),
            }

            goals.append(goal)
            print(f"Extracted: {title} ({platform})")
            continue

        # If this row has platform but no title, it's a platform header
        if (
            platform
            and not title
            and platform != "Project/platform"
            and platform != "OVERALL RESOURCING TOTALS"
        ):
            current_platform = platform
            current_lead = lead
            continue

        # Check if this is a goal row under a platform (has title but no platform)
        if title and not platform and current_platform:
            # Skip header rows and totals
            if title not in ["TOTAL", "Goal/Milestone", "@"]:
                # Extract goal data
                priority = row.iloc[4] if pd.notna(row.iloc[4]) else None
                size = row.iloc[5] if pd.notna(row.iloc[5]) else None
                status = row.iloc[6] if pd.notna(row.iloc[6]) else None
                description = row.iloc[7] if pd.notna(row.iloc[7]) else None
                success_criteria = (
                    row.iloc[8] if pd.notna(row.iloc[8]) else None
                )
                risks = row.iloc[9] if pd.notna(row.iloc[9]) else None
                resource_summary = (
                    row.iloc[38] if pd.notna(row.iloc[38]) else None
                )

                goal = {
                    "platform": current_platform,
                    "lead": current_lead,
                    "title": str(title).strip(),
                    "priority": str(priority).strip() if priority else None,
                    "size": str(size).strip() if size else None,
                    "description": (
                        str(description).strip() if description else None
                    ),
                    "status": str(status).strip() if status else None,
                    "success_criteria": (
                        str(success_criteria).strip()
                        if success_criteria
                        else None
                    ),
                    "risks": str(risks).strip() if risks else None,
                    "resource_summary": (
                        str(resource_summary).strip()
                        if resource_summary
                        else None
                    ),
                }

                goals.append(goal)
                print(f"Extracted: {title} ({current_platform})")

    return goals


def main():
    """Main function"""
    print("Extracting all goals from Excel file...")

    goals = extract_all_goals()

    print(f"\nTotal goals extracted: {len(goals)}")

    # Save to JSON file
    with open("q3_goals_complete.json", "w") as f:
        json.dump(goals, f, indent=2)

    print(f"Saved {len(goals)} goals to q3_goals_complete.json")

    # Show platform breakdown
    platform_counts = {}
    for goal in goals:
        platform = goal["platform"]
        platform_counts[platform] = platform_counts.get(platform, 0) + 1

    print("\nPlatform breakdown:")
    for platform, count in sorted(platform_counts.items()):
        print(f"  {platform}: {count} goals")


if __name__ == "__main__":
    main()
