import os
import requests
import json

TOKEN = os.environ["GITHUB_TOKEN"]
ORG = "AllenNeuralDynamics"
PROJECT_NUMBER = 54

QUERY = """
query($org: String!, $number: Int!, $cursor: String) {
  organization(login: $org) {
    projectV2(number: $number) {
      title
      fields(first: 20) {
        nodes {
          ... on ProjectV2Field {
            id
            name
          }
          ... on ProjectV2SingleSelectField {
            id
            name
            options {
              id
              name
            }
          }
        }
      }
      items(first: 50, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          content {
            ... on Issue {
              title
              number
              state
              url
              repository { name }
            }
            ... on PullRequest {
              title
              number
              state
              url
              repository { name }
            }
            ... on DraftIssue {
              title
            }
          }
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldTextValue {
                text
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldDateValue {
                date
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldIterationValue {
                title
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


def run_query(cursor=None):
    response = requests.post(
        "https://api.github.com/graphql",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json={"query": QUERY, "variables": {"org": ORG, "number": PROJECT_NUMBER, "cursor": cursor}},
    )
    response.raise_for_status()
    data = response.json()
    if "errors" in data:
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]["organization"]["projectV2"]


def main():
    project = run_query()
    print(f"Project: {project['title']}\n")

    print("=== Fields ===")
    for field in project["fields"]["nodes"]:
        if "options" in field:
            opts = ", ".join(o["name"] for o in field["options"])
            print(f"  {field['name']} (single-select): {opts}")
        elif "name" in field:
            print(f"  {field['name']}")

    print("\n=== Items ===")
    all_items = project["items"]["nodes"]
    page_info = project["items"]["pageInfo"]

    while page_info["hasNextPage"]:
        next_page = run_query(cursor=page_info["endCursor"])
        all_items += next_page["items"]["nodes"]
        page_info = next_page["items"]["pageInfo"]

    for item in all_items:
        content = item.get("content") or {}
        title = content.get("title", "(no title)")
        repo = content.get("repository", {}).get("name", "")
        number = content.get("number", "")
        state = content.get("state", "")
        url = content.get("url", "")

        fields = {}
        for fv in item["fieldValues"]["nodes"]:
            field_name = fv.get("field", {}).get("name")
            value = fv.get("text") or fv.get("name") or fv.get("date") or fv.get("title")
            if field_name and value:
                fields[field_name] = value

        label = f"[{repo}#{number}]" if number else ""
        print(f"{label} {title} ({state})")
        if fields:
            for k, v in fields.items():
                print(f"    {k}: {v}")
        if url:
            print(f"    {url}")


if __name__ == "__main__":
    main()
