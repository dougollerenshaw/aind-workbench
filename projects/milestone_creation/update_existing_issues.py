#!/usr/bin/env python3
"""
Update existing GitHub issues with success criteria and risks from the complete JSON file.
"""

import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = "AllenNeuralDynamics"
REPO_NAME = "aind-scientific-computing"


def clean_field_value(value):
    """Convert None, empty, or placeholder values to _No response_"""
    if (
        not value
        or value == "placeholder"
        or value == "None"
        or str(value).strip() == ""
    ):
        return "_No response_"
    return str(value).strip()


def convert_percentage_to_weeks(resource_summary):
    """Convert percentage allocation to weeks (10% = 1 week, minimum 1 week)"""
    if (
        not resource_summary
        or resource_summary == "placeholder"
        or resource_summary == "None"
    ):
        return "_No response_"

    # Extract percentages and convert to weeks
    import re
    import math

    def replace_percentage(match):
        percentage = float(match.group(1))
        weeks = max(
            1, math.ceil(percentage / 10)
        )  # 10% = 1 week, minimum 1 week
        return f"{match.group(0).replace(match.group(1), str(weeks))}"

    # Replace percentages with weeks (e.g., "5%" -> "1 week", "25%" -> "3 weeks")
    result = re.sub(r"(\d+(?:\.\d+)?)%", replace_percentage, resource_summary)

    # Replace "%" with " week" or " weeks" for any remaining percentages
    def format_weeks(match):
        weeks = int(match.group(1))
        if weeks == 1:
            return "1 week"
        else:
            return f"{weeks} weeks"

    result = re.sub(r"(\d+)%", format_weeks, result)

    # Split by comma and put each person on a new line
    if "," in result:
        lines = [line.strip() for line in result.split(",")]
        result = "\n".join(lines)

    return result


def clean_title(title):
    """Remove parenthetical priority and size information from titles"""
    import re

    # Remove ALL parenthetical expressions like (P0, M), (or IAMRA), etc.
    cleaned = re.sub(r"\s*\([^)]*\)\s*", " ", title)
    return cleaned.strip()


def get_existing_issues():
    """Get all existing issues from the repository"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    issues = []
    page = 1
    per_page = 100

    while True:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues"
        params = {
            "state": "all",  # Get both open and closed issues
            "page": page,
            "per_page": per_page,
        }

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        page_issues = response.json()
        if not page_issues:
            break

        issues.extend(page_issues)
        page += 1

    return issues


def update_issue_body(issue_number, new_body):
    """Update the body of an existing issue"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{issue_number}"
    data = {"body": new_body}

    response = requests.patch(url, headers=headers, json=data)
    response.raise_for_status()

    return response.json()


def main():
    """Main function"""
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN not found in environment variables")
        return

    # Load the complete goals
    with open("q3_goals_complete.json", "r") as f:
        goals = json.load(f)

    print(f"Loaded {len(goals)} goals from complete JSON")

    # Get existing issues
    print("Fetching existing issues...")
    existing_issues = get_existing_issues()
    print(f"Found {len(existing_issues)} existing issues")

    # Create a mapping of cleaned titles to goals
    goal_map = {}
    for goal in goals:
        cleaned_title = clean_title(goal["title"])
        goal_map[cleaned_title] = goal

    # Priority mapping
    priority_map = {
        "P0": "Critical (Must Complete)",
        "P1": "High (Should Complete)",
        "P2": "Medium (Nice to Have)",
        "P3": "Low (If Time Permits)",
    }

    # Platform to team mapping
    PLATFORM_TO_TEAM = {
        "Behavior": "Physiology and behavior",
        "Analysis": "Physiology and behavior",
        "Fiber Photometry": "Physiology and behavior",
        "2P Ophys": "Physiology and behavior",
        "Ephys": "Ephys",
        "Slap2": "Computer Vision",
        "SmartSPIM": "Computer Vision",
        "ExaSPIM": "Computer Vision",
        "Z1": "Computer Vision",
        "Behavior Videos": "Computer Vision",
        "Data Infrastructure": "Data Infrastructure",
        "Dataverse - PowerApps": "Data Infrastructure",
        "Data & Outreach": "Data and Outreach",
    }

    updated_count = 0
    skipped_count = 0

    for issue in existing_issues:
        # Skip pull requests
        if "pull_request" in issue:
            continue

        issue_title = issue["title"]
        cleaned_issue_title = clean_title(issue_title)

        # Find matching goal
        if cleaned_issue_title in goal_map:
            goal = goal_map[cleaned_issue_title]

            # Get team
            team = PLATFORM_TO_TEAM.get(goal["platform"], "_No response_")

            # Create new issue body with updated content
            new_body = f"""### Detailed Description

{clean_field_value(goal.get('description'))}

### Resource Allocation

{convert_percentage_to_weeks(goal.get('resource_summary', 'placeholder'))}

### Priority Level

{priority_map.get(goal['priority'], 'Medium (Nice to Have)')}

### Team

{team}

### Success Criteria

{clean_field_value(goal.get('success_criteria'))}

### Dependencies

_No response_

### Risks & Mitigation

{clean_field_value(goal.get('risks'))}

### Related Issues & Implementation Work

_No response_
"""

            # Update the issue
            try:
                update_issue_body(issue["number"], new_body)
                print(f"✅ Updated issue #{issue['number']}: {issue_title}")
                updated_count += 1
            except Exception as e:
                print(f"❌ Failed to update issue #{issue['number']}: {e}")
        else:
            print(
                f"⏭️  Skipped issue #{issue['number']}: {issue_title} (no matching goal)"
            )
            skipped_count += 1

    print(f"\n📊 Summary:")
    print(f"  Updated: {updated_count} issues")
    print(f"  Skipped: {skipped_count} issues")
    print(f"  Total processed: {updated_count + skipped_count} issues")


if __name__ == "__main__":
    main()
