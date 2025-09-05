#!/usr/bin/env python3
"""
Script to get the GitHub project ID for project number 54
"""

import requests
import os
import json


def get_project_id():
    """Get the project ID for project number 54"""

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN not set")
        print("   Set it with: export GITHUB_TOKEN='your_token_here'")
        return None

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Query to get all projects for the organization
    url = "https://api.github.com/graphql"
    query = """
    query {
      organization(login: "AllenNeuralDynamics") {
        projectsV2(first: 100) {
          nodes {
            id
            title
            number
          }
        }
      }
    }
    """

    print("🔍 Querying GitHub API for projects...")
    response = requests.post(url, headers=headers, json={"query": query})

    if response.status_code == 200:
        data = response.json()

        # Check for errors
        if "errors" in data:
            print("❌ GraphQL errors:")
            for error in data["errors"]:
                print(f"   - {error['message']}")

            # Check if it's a SAML issue
            if any("SAML" in str(error) for error in data["errors"]):
                print("\n💡 SAML Authorization Required:")
                print("   1. Go to https://github.com/settings/tokens")
                print("   2. Find your token and click 'Configure SSO'")
                print(
                    "   3. Authorize it for 'AllenNeuralDynamics' organization"
                )
                return None

            return None

        # Check if we have data
        if "data" not in data or not data["data"]["organization"]:
            print("❌ No organization data in response")
            return None

        projects = data["data"]["organization"]["projectsV2"]["nodes"]

        if not projects:
            print("❌ No projects found")
            return None

        print(f"📋 Found {len(projects)} projects:")

        # Look for project number 54
        for project in projects:
            if project and project.get("number") == 54:
                print(f"\n✅ Found project 54!")
                print(f"   Title: {project['title']}")
                print(f"   ID: {project['id']}")
                print(f"\n📝 Set this as your project ID:")
                print(f"   export GITHUB_PROJECT_ID='{project['id']}'")
                return project["id"]

        # Show all projects if we didn't find 54
        print("\n📋 All available projects:")
        for project in projects:
            if project:
                print(
                    f"   - {project['title']} (Number: {project['number']}, ID: {project['id']})"
                )

        print(f"\n❌ Project number 54 not found")
        return None

    else:
        print(f"❌ API request failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return None


if __name__ == "__main__":
    get_project_id()
