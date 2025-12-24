#!/usr/bin/env python3
"""
Generate reports from GitHub project board for PM updates
"""

import requests
import json
import os
import argparse
import csv
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
PROJECT_ID = os.getenv("GITHUB_PROJECT_ID")


def get_project_items():
    """Get all items from the project board"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }

    query = """
    query GetProjectItems($projectId: ID!) {
        node(id: $projectId) {
            ... on ProjectV2 {
                items(first: 100) {
                    nodes {
                        id
                        content {
                            ... on Issue {
                                id
                                number
                                title
                                state
                                createdAt
                                closedAt
                                url
                                body
                                labels(first: 10) {
                                    nodes {
                                        name
                                    }
                                }
                            }
                        }
                        fieldValues(first: 20) {
                            nodes {
                                ... on ProjectV2ItemFieldSingleSelectValue {
                                    field {
                                        ... on ProjectV2FieldCommon {
                                            name
                                        }
                                    }
                                    name
                                }
                                ... on ProjectV2ItemFieldDateValue {
                                    field {
                                        ... on ProjectV2FieldCommon {
                                            name
                                        }
                                    }
                                    date
                                }
                                ... on ProjectV2ItemFieldTextValue {
                                    field {
                                        ... on ProjectV2FieldCommon {
                                            name
                                        }
                                    }
                                    text
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    """

    response = requests.post(
        "https://api.github.com/graphql",
        headers=headers,
        json={"query": query, "variables": {"projectId": PROJECT_ID}},
    )

    if response.status_code != 200:
        print(f"API request failed: {response.status_code}")
        print(response.text)
        return []

    data = response.json()
    if "errors" in data:
        print(f"GraphQL errors: {data['errors']}")
        return []

    return data["data"]["node"]["items"]["nodes"]


def extract_field_value(item, field_name):
    """Extract a field value from project item"""
    for field_value in item["fieldValues"]["nodes"]:
        if field_value.get("field", {}).get("name") == field_name:
            if "name" in field_value:
                return field_value["name"]
            elif "date" in field_value:
                return field_value["date"]
            elif "text" in field_value:
                return field_value["text"]
    return None


def parse_issue_body(body):
    """Parse issue body to extract structured fields"""
    if not body:
        return {}

    fields = {}
    lines = body.split("\n")

    current_field = None
    current_content = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if this line is a field header (with or without markdown)
        field_name = line.replace("### ", "").strip()
        if field_name in [
            "Detailed Description",
            "Resource Allocation",
            "Priority Level",
            "Success Criteria",
            "Dependencies",
            "Risks & Mitigation",
            "Related Issues & Implementation Work",
        ]:
            # Save previous field
            if current_field and current_content:
                content = "\n".join(current_content).strip()
                if content.lower() in ["none", "placeholder"] or not content:
                    content = "_No response_"
                fields[current_field] = content

            # Start new field
            current_field = field_name
            current_content = []
        else:
            # Add to current field content
            if current_field:
                current_content.append(line)

    # Save last field
    if current_field and current_content:
        content = "\n".join(current_content).strip()
        if content.lower() in ["none", "placeholder"] or not content:
            content = "_No response_"
        fields[current_field] = content

    return fields


def categorize_items(items, completed_days=30, upcoming_days=30):
    """Categorize items into completed, underway, and upcoming, organized by team"""
    now = datetime.now()
    completed_cutoff = now - timedelta(days=completed_days)
    upcoming_cutoff = now + timedelta(days=upcoming_days)

    # Debug counters
    total_items = len(items)
    items_with_content = 0
    open_items = 0
    closed_items = 0
    items_with_start_dates = 0
    items_with_team = 0
    items_with_iteration = 0

    # Organize by team
    teams = {}

    for item in items:
        if not item["content"]:
            continue
        items_with_content += 1

        issue = item["content"]
        if issue["state"] != "OPEN" and issue["state"] != "CLOSED":
            continue

        if issue["state"] == "OPEN":
            open_items += 1
        elif issue["state"] == "CLOSED":
            closed_items += 1

        # Extract fields
        team = extract_field_value(item, "Team") or "Unknown"
        if team != "Unknown":
            items_with_team += 1

        iteration = extract_field_value(item, "Iteration") or "_No response_"
        if iteration != "_No response_":
            items_with_iteration += 1

        start_date_str = extract_field_value(item, "Expected Start Date")
        end_date_str = extract_field_value(item, "Expected End Date")

        if start_date_str:
            items_with_start_dates += 1

        # Parse issue body for additional fields
        body_fields = parse_issue_body(issue.get("body", ""))

        # Parse dates
        start_date = None
        end_date = None
        if start_date_str:
            try:
                start_date = datetime.fromisoformat(
                    start_date_str.replace("Z", "+00:00")
                )
            except:
                pass
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(
                    end_date_str.replace("Z", "+00:00")
                )
            except:
                pass

        item_data = {
            "title": issue["title"],
            "number": issue["number"],
            "url": issue["url"],
            "team": team,
            "iteration": iteration,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "state": issue["state"].lower(),
            "description": body_fields.get(
                "Detailed Description", "_No response_"
            ),
            "resource_allocation": body_fields.get(
                "Resource Allocation", "_No response_"
            ),
            "priority": body_fields.get("Priority Level", "_No response_"),
            "success_criteria": body_fields.get(
                "Success Criteria", "_No response_"
            ),
            "dependencies": body_fields.get("Dependencies", "_No response_"),
            "risks": body_fields.get("Risks & Mitigation", "_No response_"),
            "related_issues": body_fields.get(
                "Related Issues & Implementation Work", "_No response_"
            ),
        }

        # Initialize team if not exists
        if team not in teams:
            teams[team] = {"completed": [], "underway": [], "upcoming": []}

        # Categorize based on state and dates
        if issue["state"] == "CLOSED":
            # Check if closed recently
            if issue["closedAt"]:
                try:
                    closed_date = datetime.fromisoformat(
                        issue["closedAt"].replace("Z", "+00:00")
                    )
                    if closed_date >= completed_cutoff:
                        teams[team]["completed"].append(item_data)
                except:
                    pass
        elif issue["state"] == "OPEN":
            if start_date and start_date <= now:
                teams[team]["underway"].append(item_data)
            elif start_date and start_date <= upcoming_cutoff:
                teams[team]["upcoming"].append(item_data)

    # Debug output
    print(f"\nDebug info:")
    print(f"  Total items: {total_items}")
    print(f"  Items with content: {items_with_content}")
    print(f"  Open items: {open_items}")
    print(f"  Closed items: {closed_items}")
    print(f"  Items with start dates: {items_with_start_dates}")
    print(f"  Items with team assigned: {items_with_team}")
    print(f"  Items with iteration: {items_with_iteration}")
    print(f"  Teams found: {list(teams.keys())}")

    return teams


def generate_csv_report(teams, filename="project_report.csv"):
    """Generate CSV report organized by team"""
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)

        # Write header
        writer.writerow(
            [
                "Team",
                "Category",
                "Title",
                "Issue #",
                "Iteration",
                "Start Date",
                "End Date",
                "State",
                "Description",
                "Resource Allocation",
                "Priority",
                "Success Criteria",
                "Dependencies",
                "Risks & Mitigation",
                "Related Issues",
                "URL",
            ]
        )

        # Write data organized by team
        for team_name in sorted(teams.keys()):
            team_data = teams[team_name]

            # Write completed items
            for item in team_data["completed"]:
                writer.writerow(
                    [
                        team_name,
                        "Completed (Last 30 days)",
                        item["title"],
                        item["number"],
                        item["iteration"],
                        item["start_date"] or "",
                        item["end_date"] or "",
                        item["state"],
                        item["description"],
                        item["resource_allocation"],
                        item["priority"],
                        item["success_criteria"],
                        item["dependencies"],
                        item["risks"],
                        item["related_issues"],
                        item["url"],
                    ]
                )

            # Write underway items
            for item in team_data["underway"]:
                writer.writerow(
                    [
                        team_name,
                        "Currently Underway",
                        item["title"],
                        item["number"],
                        item["iteration"],
                        item["start_date"] or "",
                        item["end_date"] or "",
                        item["state"],
                        item["description"],
                        item["resource_allocation"],
                        item["priority"],
                        item["success_criteria"],
                        item["dependencies"],
                        item["risks"],
                        item["related_issues"],
                        item["url"],
                    ]
                )

            # Write upcoming items
            for item in team_data["upcoming"]:
                writer.writerow(
                    [
                        team_name,
                        "Upcoming (Next 30 days)",
                        item["title"],
                        item["number"],
                        item["iteration"],
                        item["start_date"] or "",
                        item["end_date"] or "",
                        item["state"],
                        item["description"],
                        item["resource_allocation"],
                        item["priority"],
                        item["success_criteria"],
                        item["dependencies"],
                        item["risks"],
                        item["related_issues"],
                        item["url"],
                    ]
                )


def generate_text_report(teams):
    """Generate text report for console output organized by team"""
    print("\n" + "=" * 80)
    print("PROJECT BOARD REPORT")
    print("=" * 80)

    for team_name in sorted(teams.keys()):
        team_data = teams[team_name]
        total_items = (
            len(team_data["completed"])
            + len(team_data["underway"])
            + len(team_data["upcoming"])
        )

        if total_items == 0:
            continue

        print(f"\n{team_name.upper()} - {total_items} items")
        print("-" * 50)

        if team_data["completed"]:
            print(
                f"\n  Completed (Last 30 days) - {len(team_data['completed'])} items:"
            )
            for item in team_data["completed"]:
                print(f"  • {item['title']} (#{item['number']})")
                print(f"    {item['url']}")

        if team_data["underway"]:
            print(
                f"\n  Currently Underway - {len(team_data['underway'])} items:"
            )
            for item in team_data["underway"]:
                print(f"  • {item['title']} (#{item['number']})")
                print(f"    Start: {item['start_date'] or 'Not set'}")
                print(f"    {item['url']}")

        if team_data["upcoming"]:
            print(
                f"\n  Upcoming (Next 30 days) - {len(team_data['upcoming'])} items:"
            )
            for item in team_data["upcoming"]:
                print(f"  • {item['title']} (#{item['number']})")
                print(f"    Start: {item['start_date'] or 'Not set'}")
                print(f"    {item['url']}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate project board reports"
    )
    parser.add_argument(
        "--completed-days",
        type=int,
        default=30,
        help="Days to look back for completed items (default: 30)",
    )
    parser.add_argument(
        "--upcoming-days",
        type=int,
        default=30,
        help="Days to look ahead for upcoming items (default: 30)",
    )
    parser.add_argument(
        "--output",
        choices=["csv", "text", "both"],
        default="both",
        help="Output format (default: both)",
    )
    parser.add_argument(
        "--filename",
        default="project_report.csv",
        help="CSV filename (default: project_report.csv)",
    )

    args = parser.parse_args()

    # Validate environment variables
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN not set in .env file")
        return

    if not PROJECT_ID:
        print("Error: GITHUB_PROJECT_ID not set in .env file")
        return

    print("Fetching project data...")
    items = get_project_items()

    if not items:
        print("No items found or API error")
        return

    print(f"Found {len(items)} items")

    # Categorize items
    teams = categorize_items(items, args.completed_days, args.upcoming_days)

    # Debug: Show what we found
    total_categorized = sum(
        len(team_data["completed"])
        + len(team_data["underway"])
        + len(team_data["upcoming"])
        for team_data in teams.values()
    )
    print(f"Categorized {total_categorized} items across {len(teams)} teams")

    if total_categorized == 0:
        print("\nNo items matched the criteria. This could be because:")
        print("- No items have been closed in the last 30 days")
        print("- No open items have start dates before today")
        print("- No open items have start dates in the next 30 days")
        print("\nTry running with different date ranges:")
        print(
            "  python generate_project_report.py --completed-days 90 --upcoming-days 90"
        )

    # Generate reports
    if args.output in ["text", "both"]:
        generate_text_report(teams)

    if args.output in ["csv", "both"]:
        generate_csv_report(teams, args.filename)
        print(f"\nCSV report saved to: {args.filename}")


if __name__ == "__main__":
    main()
