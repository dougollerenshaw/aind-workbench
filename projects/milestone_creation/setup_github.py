#!/usr/bin/env python3
"""
Setup script for GitHub project board integration

This script helps you set up the required environment variables and get the project ID.
"""

import os
import requests
import json


def get_project_id():
    """Get the project ID from GitHub API"""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN not set. Please set it first:")
        print("   export GITHUB_TOKEN='your_token_here'")
        return None

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Get projects for the organization
    url = "https://api.github.com/graphql"
    query = """
    query {
      organization(login: "AllenNeuralDynamics") {
        projectsV2(first: 10) {
          nodes {
            id
            title
            number
          }
        }
      }
    }
    """

    response = requests.post(url, headers=headers, json={"query": query})

    if response.status_code == 200:
        data = response.json()
        print(f"Debug: API response: {data}")

        if "errors" in data:
            print(f"❌ GraphQL errors: {data['errors']}")
            return None

        if "data" not in data:
            print(f"❌ No data in response: {data}")
            return None

        projects = data["data"]["organization"]["projectsV2"]["nodes"]

        print("📋 Available projects:")
        for project in projects:
            print(
                f"  - {project['title']} (ID: {project['id']}, Number: {project['number']})"
            )

        # Look for the Scientific Computing Roadmap project
        for project in projects:
            if "Scientific Computing" in project["title"]:
                print(
                    f"\n✅ Found Scientific Computing project: {project['id']}"
                )
                return project["id"]

        print("\n❌ Could not find Scientific Computing project")
        return None
    else:
        print(f"❌ Failed to get projects: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def main():
    print("🔧 GitHub Project Board Setup")
    print("=" * 40)

    # Check current environment
    token = os.getenv("GITHUB_TOKEN")
    project_id = os.getenv("GITHUB_PROJECT_ID")

    print(f"Current GITHUB_TOKEN: {'✅ Set' if token else '❌ Not set'}")
    print(
        f"Current GITHUB_PROJECT_ID: {'✅ Set' if project_id else '❌ Not set'}"
    )

    if not token:
        print("\n📝 To set your GitHub token:")
        print("1. Go to https://github.com/settings/tokens")
        print("2. Generate a new token with 'repo' and 'project' permissions")
        print("3. Run: export GITHUB_TOKEN='your_token_here'")
        return

    if not project_id:
        print("\n🔍 Getting project ID...")
        project_id = get_project_id()
        if project_id:
            print(f"\n📝 To set the project ID, run:")
            print(f"   export GITHUB_PROJECT_ID='{project_id}'")
        return

    print("\n✅ All environment variables are set!")
    print("You can now run the populate script.")


if __name__ == "__main__":
    main()
