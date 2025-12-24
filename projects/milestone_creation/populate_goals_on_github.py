import pandas as pd
import requests
import json
import time
import os
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration - load from environment variables
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = "AllenNeuralDynamics"
REPO_NAME = "aind-scientific-computing"
PROJECT_ID = os.getenv("GITHUB_PROJECT_ID")  # Load from environment variable

# Test repository configuration
TEST_REPO_OWNER = "dougollerenshaw"
TEST_REPO_NAME = "aind-test-issues"
TEST_PROJECT_ID = "PVT_kwHOATBT-s4BCsRW"  # The test project we just created

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


def clean_field_value(value):
    """Convert None, empty, or placeholder values to _No response_"""
    if (
        not value
        or value == "None"
        or value == "placeholder"
        or value == "none"
    ):
        return "_No response_"
    return value


def clean_title(title):
    """Remove parenthetical priority and size information from titles"""
    import re

    # Remove patterns like (P2, M), (P1, L), etc.
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", title)
    return cleaned.strip()


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


def create_github_issue(
    goal,
    reopen_closed=False,
    force_create=False,
    team=None,
    test_repo=False,
    test_issue=False,
):
    """Create a GitHub issue from a Q3 goal"""

    # Check if issue already exists (unless forcing creation)
    if not force_create:
        existing_issue = check_existing_issue(clean_title(goal["title"]))
        if existing_issue:
            if existing_issue["state"] == "closed" and reopen_closed:
                # Reopen the closed issue
                headers = {
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json",
                }

                reopen_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{existing_issue['number']}"
                reopen_data = {"state": "open"}

                response = requests.patch(
                    reopen_url, headers=headers, json=reopen_data
                )
                if response.status_code == 200:
                    print(
                        f"Reopened issue: #{existing_issue['number']} - {clean_title(goal['title'])}"
                    )
                    return existing_issue
                else:
                    print(
                        f"Failed to reopen issue: {response.status_code} - {response.text}"
                    )
                    return None
            else:
                print(
                    f"Issue already exists: #{existing_issue['number']} - {clean_title(goal['title'])}"
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
    # Create issue body
    if test_issue:
        issue_body = """### Detailed Description

This is a test issue to verify project board field functionality.

### Resource Allocation

_No response_

### Priority Level

Medium (Nice to Have)

### Team

_No response_

### Success Criteria

Test that all project board fields can be set properly.

### Dependencies

_No response_

### Risks & Mitigation

_No response_

### Related Issues & Implementation Work

_No response_
"""
    else:
        issue_body = f"""### Detailed Description

{goal.get('description', '_No response_')}

### Resource Allocation

{convert_percentage_to_weeks(goal.get('resource_summary', 'placeholder'))}

### Priority Level

{priority_map.get(goal['priority'], 'Medium (Nice to Have)')}

### Team

{team or '_No response_'}

### Success Criteria

{goal.get('success_criteria', '_No response_')}

### Dependencies

_No response_

### Risks & Mitigation

{goal.get('risks', '_No response_')}

### Related Issues & Implementation Work

_No response_
"""

    # Create a test issue title for testing
    if test_issue:
        title = "TEST ISSUE"
    else:
        title = clean_title(goal["title"])

    issue_data = {
        "title": title,
        "body": issue_body,
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
        addProjectV2ItemById(input: {
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

    item_id = result["data"]["addProjectV2ItemById"]["item"]["id"]

    # Wait a moment for the item to be fully added
    time.sleep(2)

    # Set custom fields - use different field IDs for test vs real project
    if PROJECT_ID == TEST_PROJECT_ID:
        # Test project field IDs
        team_field_id = "PVTSSF_lAHOATBT-s4BCsRWzg01mnI"
        iteration_field_id = None  # Skip iteration field - set manually
        start_date_field_id = "PVTF_lAHOATBT-s4BCsRWzg01mkY"
        end_date_field_id = "PVTF_lAHOATBT-s4BCsRWzg01mkc"
    else:
        # Real project field IDs
        team_field_id = "PVTSSF_lADOBa47bs4AX5qJzgmBBnE"
        iteration_field_id = "PVTIF_lADOBa47bs4AX5qJzgPR3nU"
        start_date_field_id = "PVTF_lADOBa47bs4AX5qJzg0e8Bc"
        end_date_field_id = "PVTF_lADOBa47bs4AX5qJzg0e8DE"

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

    # Set team field (only if field exists)
    if team_field_id:
        if PROJECT_ID == TEST_PROJECT_ID:
            # Test project team options
            team_option_map = {
                "Data Infrastructure": "05a25161",
                "Physiology and behavior": "f34c59d0",
                "Imaging": "926873bb",
                "Electrophysiology": "6478a318",
                "Data Science": "2c5939a1",
                "Platform": "8b7dfe50",
            }
            team_option_id = team_option_map.get(team, "f34c59d0")
        else:
            # Real project team options
            team_option_map = {
                "Data Infrastructure": "3ac55192",
                "Data and Outreach": "ebd9b6c9",
                "Computer Vision": "263d29f7",
                "Physiology and behavior": "b1922bdb",
                "Ephys": "d1a2f146",
            }
            team_option_id = team_option_map.get(team, "b1922bdb")

        team_response = requests.post(
            "https://api.github.com/graphql",
            headers=headers,
            json={
                "query": set_team_mutation,
                "variables": {
                    "projectId": PROJECT_ID,
                    "itemId": item_id,
                    "fieldId": team_field_id,
                    "value": team_option_id,
                },
            },
        )
        print(f"Team field response: {team_response.status_code}")
        if team_response.status_code != 200:
            print(f"Team field error: {team_response.text}")
    else:
        print("Skipping team field - field doesn't exist")

    # Set iteration field
    if iteration_field_id:
        if PROJECT_ID == TEST_PROJECT_ID:
            # Test project - skip iteration field, set manually
            print(
                "Skipping iteration field for test project - set manually in UI"
            )
        else:
            # Real project - iteration field with actual iteration IDs
            iteration_id_map = {
                "25Q1": "31a0a951",
                "25Q2": "2fae6a19",
                "25Q3": "18d3530b",
                "25Q4": "c7c7e70b",
            }

            iteration_id = iteration_id_map.get(iteration, "18d3530b")

            set_iteration_mutation = """
            mutation SetIteration($projectId: ID!, $itemId: ID!, $fieldId: ID!, $iterationId: ID!) {
                updateProjectV2ItemFieldValue(input: {
                    projectId: $projectId
                    itemId: $itemId
                    fieldId: $fieldId
                    value: {
                        iterationId: $iterationId
                    }
                }) {
                    projectV2Item {
                        id
                    }
                }
            }
            """

            iteration_response = requests.post(
                "https://api.github.com/graphql",
                headers=headers,
                json={
                    "query": set_iteration_mutation,
                    "variables": {
                        "projectId": PROJECT_ID,
                        "itemId": item_id,
                        "fieldId": iteration_field_id,
                        "iterationId": iteration_id,
                    },
                },
            )
            print(
                f"Iteration field response: {iteration_response.status_code}"
            )
            if iteration_response.status_code != 200:
                print(f"Iteration field error: {iteration_response.text}")

    # Set start date (July 1, 2025)
    start_date_response = requests.post(
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
    print(f"Start date response: {start_date_response.status_code}")
    if start_date_response.status_code != 200:
        print(f"Start date error: {start_date_response.text}")

    # Set end date (September 30, 2025)
    end_date_response = requests.post(
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
    print(f"End date response: {end_date_response.status_code}")
    if end_date_response.status_code != 200:
        print(f"End date error: {end_date_response.text}")

    print(
        f"Added issue #{issue_number} to project with team={team}, iteration={iteration}"
    )
    return True


def main(
    test_mode=False,
    reopen_closed=False,
    force_create=False,
    limit=None,
    test_repo=False,
    test_issue=False,
    skip_project_board=False,
):
    """Main function to import all Q3 goals"""

    global REPO_OWNER, REPO_NAME, PROJECT_ID

    # Validate environment variables
    if not GITHUB_TOKEN:
        print("Error: GITHUB_TOKEN environment variable not set")
        print("   Please set it with: export GITHUB_TOKEN='your_token_here'")
        return

    if not PROJECT_ID:
        print("Error: GITHUB_PROJECT_ID environment variable not set")
        print(
            "   Please set it with: export GITHUB_PROJECT_ID='your_project_id_here'"
        )
        return

    # Set repository and project based on test_repo flag
    if test_repo:
        REPO_OWNER = TEST_REPO_OWNER
        REPO_NAME = TEST_REPO_NAME
        PROJECT_ID = TEST_PROJECT_ID
        print(f"Using TEST repository: {REPO_OWNER}/{REPO_NAME}")
        print(f"Using TEST project: {PROJECT_ID}")

    # Load goals from JSON file
    try:
        with open("q3_goals_complete.json", "r") as f:
            goals = json.load(f)
    except FileNotFoundError:
        print(
            "Error: q3_goals_complete.json not found. Please run the parsing script first."
        )
        return
    except json.JSONDecodeError:
        print("Error: Invalid JSON in q3_goals_complete.json")
        return

    if test_mode:
        print("TEST MODE: Processing only the first goal...")
        goals = goals[:1]
    elif limit:
        print(f"LIMIT MODE: Processing only the first {limit} goals...")
        goals = goals[:limit]

    print(f"Starting import of {len(goals)} Q3 goals...")

    for i, goal in enumerate(goals):
        print(
            f"\nProcessing goal {i+1}/{len(goals)}: {clean_title(goal['title'])}"
        )

        # Map platform to team
        team = PLATFORM_TO_TEAM.get(goal["platform"], "Data Infrastructure")

        # Create the GitHub issue
        issue = create_github_issue(
            goal, reopen_closed, force_create, team, test_repo, test_issue
        )
        if not issue:
            print(f"Failed to create issue for: {clean_title(goal['title'])}")
            continue

        if skip_project_board:
            print(
                f"Successfully created issue: #{issue['number']} - {clean_title(goal['title'])}"
            )
            print(f"Team: {team} (add manually to project board)")
        else:
            # Add to project and set fields
            success = add_to_project_and_set_fields(
                issue["number"], issue["node_id"], team
            )

            if success:
                print(f"Successfully imported: {goal['title']}")
            else:
                print(f"Failed to add to project: {goal['title']}")

        # Rate limiting - be nice to GitHub
        time.sleep(1)

        if test_mode:
            print("Test mode: stopping after first goal")
            break

    print(f"\nImport complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import Q3 goals to GitHub issues"
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Test mode: process only the first goal",
    )
    parser.add_argument(
        "--reopen-closed",
        action="store_true",
        help="Reopen closed issues if they already exist",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force creation of new issues even if duplicates exist",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of issues to create (e.g., --limit 10)",
    )
    parser.add_argument(
        "--test-repo",
        action="store_true",
        help="Use test repository instead of main repository",
    )
    parser.add_argument(
        "--test-issue",
        action="store_true",
        help="Create test issues with fake content instead of real goal data",
    )
    parser.add_argument(
        "--skip-project-board",
        action="store_true",
        help="Skip adding issues to project board (create issues only)",
    )

    args = parser.parse_args()
    main(
        test_mode=args.test_mode,
        reopen_closed=args.reopen_closed,
        force_create=args.force,
        limit=args.limit,
        test_repo=args.test_repo,
        test_issue=args.test_issue,
        skip_project_board=args.skip_project_board,
    )
