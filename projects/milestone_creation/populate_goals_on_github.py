import pandas as pd
import requests
import json
import time
import os
from datetime import datetime

# Configuration - load from environment variables
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = "AllenNeuralDynamics"
REPO_NAME = "aind-scientific-computing"
PROJECT_ID = os.getenv("GITHUB_PROJECT_ID")  # Load from environment variable

# Platform to Team mapping - updated based on the actual platforms in the data
PLATFORM_TO_TEAM = {
    "Behavior": "Physiology and behavior",
    "Analysis": "Physiology and behavior",
    "Fiber Photometry": "Physiology and behavior",
    "Data Infrastructure": "Data Infrastructure",
    "Data & Outreach": "Data and Outreach",
    "Computer Vision": "Computer Vision",
    "Ephys": "Ephys",
    "2P Ophys": "Physiology and behavior",
    "Behavior Videos": "Computer Vision",
    "SmartSPIM": "Computer Vision",
    "ExaSPIM": "Computer Vision",
    "Z1": "Computer Vision",
    "Slap2": "Computer Vision",
    "Dataverse - PowerApps": "Data Infrastructure",
}


def convert_percentage_to_hours(resource_summary):
    """Convert percentage allocation to hours (5% = 20 hours)"""
    if not resource_summary or resource_summary == "placeholder":
        return resource_summary

    # Extract percentages and convert to hours
    import re

    def replace_percentage(match):
        percentage = float(match.group(1))
        hours = int(percentage * 4)  # 5% = 20 hours, so multiply by 4
        return f"{match.group(0).replace(match.group(1), str(hours))}"

    # Replace percentages with hours (e.g., "5%" -> "20 hours")
    result = re.sub(r"(\d+(?:\.\d+)?)%", replace_percentage, resource_summary)

    # Replace "%" with " hours" for any remaining percentages
    result = result.replace("%", " hours")

    return result


def check_existing_issue(title):
    """Check if an issue with the given title already exists"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Search for issues with the exact title
    search_query = f'repo:{REPO_OWNER}/{REPO_NAME} "{title}" in:title'
    url = f"https://api.github.com/search/issues?q={search_query}"

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        results = response.json()
        if results["total_count"] > 0:
            # Check if any of the results have the exact title
            for item in results["items"]:
                if item["title"] == title:
                    return item
    return None


def create_github_issue(goal):
    """Create a GitHub issue from a Q3 goal"""

    # Check if issue already exists
    existing_issue = check_existing_issue(goal["title"])
    if existing_issue:
        print(
            f"⚠️  Issue already exists: #{existing_issue['number']} - {goal['title']}"
        )
        return existing_issue

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Map priority to our template format
    priority_map = {
        "P0": "Critical (Must Complete)",
        "P1": "High (Should Complete)",
        "P2": "Medium (Nice to Have)",
        "P3": "Low (If Time Permits)",
    }

    # Format the issue body to match our milestone template
    issue_body = f"""### Detailed Description

{goal.get('description', 'placeholder')}

### Resource Allocation

{convert_percentage_to_hours(goal.get('resource_summary', 'placeholder'))}

### Priority Level

{priority_map.get(goal['priority'], 'Medium (Nice to Have)')}

### Success Criteria

{goal.get('success_criteria', 'placeholder')}

### Dependencies

{goal.get('risks', 'placeholder')}

### Risks & Mitigation

{goal.get('risks', 'placeholder')}

### Related Issues & Implementation Work

None
"""

    issue_data = {
        "title": goal["title"],
        "body": issue_body,
        "labels": ["milestone"],
    }

    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues"
    response = requests.post(url, headers=headers, json=issue_data)

    if response.status_code == 201:
        return response.json()
    else:
        print(
            f"Failed to create issue: {response.status_code} - {response.text}"
        )
        return None


def add_to_project_and_set_fields(
    issue_number, issue_node_id, team, iteration="25Q3"
):
    """Add issue to project board and set custom fields"""

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }

    # Add to project
    add_mutation = """
    mutation AddToProject($projectId: ID!, $contentId: ID!) {
        addProjectV2ItemByContentId(input: {
            projectId: $projectId
            contentId: $contentId
        }) {
            item {
                id
            }
        }
    }
    """

    variables = {"projectId": PROJECT_ID, "contentId": issue_node_id}

    response = requests.post(
        "https://api.github.com/graphql",
        headers=headers,
        json={"query": add_mutation, "variables": variables},
    )

    if response.status_code != 200:
        print(f"Failed to add issue to project: {response.text}")
        return False

    result = response.json()
    if "errors" in result:
        print(f"GraphQL errors: {result['errors']}")
        return False

    item_id = result["data"]["addProjectV2ItemByContentId"]["item"]["id"]

    # Wait a moment for the item to be fully added
    time.sleep(2)

    # Now set the custom fields
    # You'll need to get the actual field IDs from your project
    # Use the GraphQL query in the setup instructions to find these
    team_field_id = "REPLACE_WITH_ACTUAL_TEAM_FIELD_ID"
    iteration_field_id = "REPLACE_WITH_ACTUAL_ITERATION_FIELD_ID"
    start_date_field_id = "REPLACE_WITH_ACTUAL_START_DATE_FIELD_ID"
    end_date_field_id = "REPLACE_WITH_ACTUAL_END_DATE_FIELD_ID"

    # Set team field
    set_team_mutation = """
    mutation SetTeam($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: String!) {
        updateProjectV2ItemFieldValue(input: {
            projectId: $projectId
            itemId: $itemId
            fieldId: $fieldId
            value: {
                singleSelectOptionId: $value
            }
        }) {
            projectV2Item {
                id
            }
        }
    }
    """

    # Set dates
    set_date_mutation = """
    mutation SetDate($projectId: ID!, $itemId: ID!, $fieldId: ID!, $date: Date!) {
        updateProjectV2ItemFieldValue(input: {
            projectId: $projectId
            itemId: $itemId
            fieldId: $fieldId
            value: {
                date: $date
            }
        }) {
            projectV2Item {
                id
            }
        }
    }
    """

    # Set start date (July 1, 2025)
    requests.post(
        "https://api.github.com/graphql",
        headers=headers,
        json={
            "query": set_date_mutation,
            "variables": {
                "projectId": PROJECT_ID,
                "itemId": item_id,
                "fieldId": start_date_field_id,
                "date": "2025-07-01",
            },
        },
    )

    # Set end date (September 30, 2025)
    requests.post(
        "https://api.github.com/graphql",
        headers=headers,
        json={
            "query": set_date_mutation,
            "variables": {
                "projectId": PROJECT_ID,
                "itemId": item_id,
                "fieldId": end_date_field_id,
                "date": "2025-09-30",
            },
        },
    )

    print(
        f"Added issue #{issue_number} to project with team={team}, iteration={iteration}"
    )
    return True


def main(test_mode=False):
    """Main function to import all Q3 goals"""

    # Validate environment variables
    if not GITHUB_TOKEN:
        print("❌ Error: GITHUB_TOKEN environment variable not set")
        print("   Please set it with: export GITHUB_TOKEN='your_token_here'")
        return

    if not PROJECT_ID:
        print("❌ Error: GITHUB_PROJECT_ID environment variable not set")
        print(
            "   Please set it with: export GITHUB_PROJECT_ID='your_project_id_here'"
        )
        return

    # Load goals from JSON file
    try:
        with open("q3_goals.json", "r") as f:
            goals = json.load(f)
    except FileNotFoundError:
        print(
            "Error: q3_goals.json not found. Please run the parsing script first."
        )
        return
    except json.JSONDecodeError:
        print("Error: Invalid JSON in q3_goals.json")
        return

    if test_mode:
        print("🧪 TEST MODE: Processing only the first goal...")
        goals = goals[:1]

    print(f"Starting import of {len(goals)} Q3 goals...")

    for i, goal in enumerate(goals):
        print(f"\nProcessing goal {i+1}/{len(goals)}: {goal['title']}")

        # Create the GitHub issue
        issue = create_github_issue(goal)
        if not issue:
            print(f"Failed to create issue for: {goal['title']}")
            continue

        # Map platform to team
        team = PLATFORM_TO_TEAM.get(goal["platform"], "Data Infrastructure")

        # Add to project and set fields
        success = add_to_project_and_set_fields(
            issue["number"], issue["node_id"], team
        )

        if success:
            print(f"✅ Successfully imported: {goal['title']}")
        else:
            print(f"❌ Failed to add to project: {goal['title']}")

        # Rate limiting - be nice to GitHub
        time.sleep(1)

        if test_mode:
            print("🧪 Test mode: stopping after first goal")
            break

    print(f"\n🎉 Import complete!")


if __name__ == "__main__":
    # Before running, you need to:
    # 1. Set environment variables for GitHub credentials
    # 2. Get the actual custom field IDs from your project
    # 3. Ensure q3_goals.json exists (run parse_excel_goals.py first)

    print("⚠️  Before running this script:")
    print("1. Set your GitHub token: export GITHUB_TOKEN='your_token_here'")
    print(
        "2. Set your project ID: export GITHUB_PROJECT_ID='your_project_id_here'"
    )
    print("3. Get custom field IDs from project settings")
    print("4. Ensure q3_goals.json exists (run parse_excel_goals.py first)")
    print("\n📝 Usage:")
    print("  - Test mode (create 1 issue): main(test_mode=True)")
    print("  - Full import (create all issues): main()")

    # Uncomment to run:
    # main(test_mode=True)  # Test with just one goal
    # main()  # Import all goals
