#!/usr/bin/env python3
"""
Build a CSV matrix of open SciComp Goal roadmap items vs repos.
Rows = open Goal issues in aind-scientific-computing (from project board #54)
Columns = repos that appear as sub-issue sources across open Goal issues (guaranteed non-empty)
Cell = "X" if that open roadmap item has at least one sub-issue in that repo
"""
import csv
import os
import requests

TOKEN = os.environ["GITHUB_TOKEN"]
ORG = "AllenNeuralDynamics"
SCICOMP_REPO = "aind-scientific-computing"
PROJECT_NUMBER = 54
OUTPUT_FILE = "repo_matrix.csv"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
}

# --- GraphQL: fetch all project board items ---

PROJECT_QUERY = """
query($org: String!, $number: Int!, $cursor: String) {
  organization(login: $org) {
    projectV2(number: $number) {
      items(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          content {
            ... on Issue {
              number
              title
              state
              issueType { name }
              repository { name }
              url
            }
          }
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2FieldCommon { name } }
              }
            }
          }
        }
      }
    }
  }
}
"""


def graphql(query, variables):
    resp = requests.post(
        "https://api.github.com/graphql",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"query": query, "variables": variables},
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data


def fetch_all_project_items():
    items = []
    cursor = None
    while True:
        data = graphql(PROJECT_QUERY, {"org": ORG, "number": PROJECT_NUMBER, "cursor": cursor})
        page = data["data"]["organization"]["projectV2"]["items"]
        items += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return items


def get_team_field(item):
    for fv in item["fieldValues"]["nodes"]:
        if fv.get("field", {}).get("name") == "Team":
            return fv.get("name", "")
    return ""


def get_sub_issue_repos(_, issue_number):
    """Fetch sub-issues for a given issue in aind-scientific-computing and return repo names."""
    url = f"https://api.github.com/repos/{ORG}/{SCICOMP_REPO}/issues/{issue_number}/sub_issues"
    repos = set()
    page = 1
    while True:
        resp = requests.get(url, headers=HEADERS, params={"per_page": 100, "page": page})
        resp.raise_for_status()
        sub_issues = resp.json()
        if not sub_issues:
            break
        for si in sub_issues:
            repo_url = si.get("repository_url", "")
            repo_name = repo_url.split("/")[-1]
            if repo_name and repo_name != SCICOMP_REPO:
                repos.add(repo_name)
        page += 1
    return repos


def main():
    print("Fetching project board items...")
    all_items = fetch_all_project_items()

    # Extract Goal issues from aind-scientific-computing
    goal_issues = []
    for item in all_items:
        content = item.get("content")
        if not content:
            continue
        if content.get("repository", {}).get("name") != SCICOMP_REPO:
            continue
        issue_type = (content.get("issueType") or {}).get("name", "")
        if issue_type != "Goal":
            continue
        team = get_team_field(item)
        goal_issues.append({
            "number": content["number"],
            "title": content["title"],
            "state": content["state"],
            "url": content["url"],
            "team": team,
        })

    # Filter to open Goal issues only
    open_goals = [i for i in goal_issues if i["state"] == "OPEN"]
    print(f"Found {len(open_goals)} open Goal issues.")

    # Fetch sub-issue repos only for open goals
    print("Fetching sub-issues...")
    sub_issues_by_number = {}
    for issue in open_goals:
        n = issue["number"]
        repos = get_sub_issue_repos(None, n)
        sub_issues_by_number[n] = repos
        print(f"  #{n}: {len(repos)} repos")

    # Only include columns that have at least one X
    all_repos = set()
    for repos in sub_issues_by_number.values():
        all_repos.update(repos)
    repos_sorted = sorted(all_repos)

    # Sort rows by team, then issue number
    open_goals.sort(key=lambda i: (i["team"] or "zzz", i["number"]))

    print(f"\n{len(open_goals)} rows × {len(repos_sorted)} columns")

    # Write CSV
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Team", "Issue", "Title", "URL"] + repos_sorted)
        for issue in open_goals:
            repos_for_issue = sub_issues_by_number[issue["number"]]
            row = [
                issue["team"],
                f"#{issue['number']}",
                issue["title"],
                issue["url"],
            ] + ["X" if r in repos_for_issue else "" for r in repos_sorted]
            writer.writerow(row)

    print(f"\nWritten to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
