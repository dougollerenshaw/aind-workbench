#!/usr/bin/env python3
"""
Test script to try different project IDs
"""

import requests
import os


def test_project_id(project_id):
    """Test if a project ID works"""

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN not set")
        return False

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Try to get project info
    url = "https://api.github.com/graphql"
    query = f"""
    query {{
      projectV2(id: "{project_id}") {{
        id
        title
        number
      }}
    }}
    """

    response = requests.post(url, headers=headers, json={"query": query})

    if response.status_code == 200:
        data = response.json()
        if "data" in data and data["data"]["projectV2"]:
            project = data["data"]["projectV2"]
            print(f"✅ Project ID {project_id} works!")
            print(f"   Title: {project['title']}")
            print(f"   Number: {project['number']}")
            return True
        else:
            print(f"❌ Project ID {project_id} not found")
            if "errors" in data:
                print(f"   Errors: {data['errors']}")
    else:
        print(f"❌ API request failed: {response.status_code}")
        print(f"   Response: {response.text}")

    return False


if __name__ == "__main__":
    # Try the project ID from the original script
    test_project_id("PVT_kwHOAAH6OM4AaCOL")

    print("\nIf that didn't work, you'll need to:")
    print("1. Get the project ID from browser developer tools")
    print("2. Or authorize your token for the organization")
