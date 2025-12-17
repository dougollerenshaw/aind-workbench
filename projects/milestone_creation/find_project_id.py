#!/usr/bin/env python3
"""
Simple script to help find the GitHub project ID
"""

import requests
import os


def find_project_id():
    """Find the project ID for project number 54"""

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN not set")
        return

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Try a simpler query to get all projects
    url = "https://api.github.com/graphql"
    query = """
    query {
      organization(login: "AllenNeuralDynamics") {
        projectsV2(first: 20) {
          nodes {
            id
            title
            number
          }
        }
      }
    }
    """

    print("🔍 Querying GitHub API...")
    response = requests.post(url, headers=headers, json={"query": query})

    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

    if response.status_code == 200:
        data = response.json()
        if "data" in data and "organization" in data["data"]:
            projects = data["data"]["organization"]["projectsV2"]["nodes"]
            print(f"\n📋 Found {len(projects)} projects:")

            for project in projects:
                print(
                    f"  - {project['title']} (Number: {project['number']}, ID: {project['id']})"
                )

                # Look for project number 54
                if project["number"] == 54:
                    print(f"\n✅ Found project 54: {project['id']}")
                    print(f"   Title: {project['title']}")
                    return project["id"]
        else:
            print("❌ Unexpected response structure")
            print(f"Data: {data}")
    else:
        print(f"❌ API request failed: {response.status_code}")


if __name__ == "__main__":
    find_project_id()
