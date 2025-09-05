import pandas as pd
import json


def parse_excel_goals():
    """Parse the Excel file and extract all Q3 goals"""

    # Read the Excel file
    df = pd.read_excel("SciComp GoalsResourcing Summary.xlsx")

    goals = []
    current_platform = None
    current_lead = None

    for idx, row in df.iterrows():
        # Check if this is a platform row
        if (
            pd.notna(row["Project/goal definitions"])
            and row["Project/goal definitions"] != "Project/platform"
        ):
            if row["Project/goal definitions"] not in ["TOTAL", "NaN"]:
                current_platform = row["Project/goal definitions"]
                current_lead = (
                    row["Unnamed: 1"] if pd.notna(row["Unnamed: 1"]) else None
                )

        # Check if this is a goal row (has a title but no platform)
        elif pd.isna(row["Project/goal definitions"]) and pd.notna(
            row["Unnamed: 3"]
        ):
            title = row["Unnamed: 3"]

            # Skip if it's a TOTAL row
            if title == "TOTAL":
                continue

            # Extract other fields
            priority = (
                row["Unnamed: 4"] if pd.notna(row["Unnamed: 4"]) else None
            )
            size = row["Unnamed: 5"] if pd.notna(row["Unnamed: 5"]) else None
            status = row["Unnamed: 6"] if pd.notna(row["Unnamed: 6"]) else None
            description = (
                row["Unnamed: 7"] if pd.notna(row["Unnamed: 7"]) else None
            )
            success_criteria = (
                row["Unnamed: 9"] if pd.notna(row["Unnamed: 9"]) else None
            )
            risks = (
                row["Unnamed: 10"] if pd.notna(row["Unnamed: 10"]) else None
            )
            resource_summary = (
                row["Resourcing Summary"]
                if pd.notna(row["Resourcing Summary"])
                else None
            )

            # Create goal object
            goal = {
                "platform": current_platform,
                "lead": current_lead,
                "title": title,
                "priority": priority,
                "size": size,
                "description": description,
                "status": status,
                "success_criteria": success_criteria,
                "risks": risks,
                "resource_summary": resource_summary,
            }

            # Only add if we have essential fields
            if (
                title
                and current_platform
                and current_platform != "Project/platform"
            ):
                goals.append(goal)

    return goals


if __name__ == "__main__":
    goals = parse_excel_goals()

    # Save to JSON file
    with open("q3_goals_complete.json", "w") as f:
        json.dump(goals, f, indent=2)

    print(f"Extracted {len(goals)} goals")
    print("\nSample goals:")
    for i, goal in enumerate(goals[:5]):
        print(f"{i+1}. {goal['title']} ({goal['platform']})")
