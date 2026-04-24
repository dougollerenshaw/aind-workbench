#!/usr/bin/env python3
import os
import subprocess
import tempfile
import shutil
import time
from github import Github, GithubException

WORKFLOW_CONTENT = """\
name: Link issue to cross-repo milestone parent

on:
  issues:
    types: [milestoned]

jobs:
  link:
    runs-on: ubuntu-latest

    steps:
      - name: Link to parent issue in aind-scientific-computing
        uses: actions/github-script@v7
        with:
          github-token: ${{ secrets.SERVICE_TOKEN }}
          script: |
            const issue = context.payload.issue;
            const milestone = issue.milestone;

            if (!milestone) return;

            const targetOwner = "AllenNeuralDynamics";
            const targetRepo = "aind-scientific-computing";

            const url = milestone.description;
            const match = url?.match(/\\/issues\\/(\\d+)$/);

            if (!match) {
              console.log(`Milestone description is not a roadmap URL: ${url}`);
              return;
            }

            const parentNumber = parseInt(match[1]);

            const { data: parent } = await github.rest.issues.get({
              owner: targetOwner,
              repo: targetRepo,
              issue_number: parentNumber
            });

            if (!parent) {
              console.log(`No issue found at ${url}`);
              return;
            }

            await github.request("POST /repos/{owner}/{repo}/issues/{issue_number}/sub_issues", {
              owner: targetOwner,
              repo: targetRepo,
              issue_number: parentNumber,
              sub_issue_id: issue.id,
              headers: {
                "X-GitHub-Api-Version": "2022-11-28"
              }
            });

            console.log(`Linked issue #${issue.number} as sub-issue of ${targetRepo}#${parentNumber}`);
"""

REPOS = [
    # "aind-data-schema",
    # "aind-data-schema-models",
    # "aind-metadata-upgrader",
    # "aind-metadata-utils",
    # "aind-metadata-viz",
    # "aind-metadata-validator",
    # "aind-qc-portal",
    "aind-qcportal-schema",
    # "zombie",
    # "zombie-squirrel",
    # "aind-software-docs",
    # "aind-data-mcp",
    # "milestone-testing"
]

ORG = "AllenNeuralDynamics"
BRANCH = "feat-add-ticket-linking-workflow"
WORKFLOW_PATH = ".github/workflows/link-issues-by-milestone.yml"
PR_TITLE = "Add ticket linking workflow"
PR_BODY = (
    "Adds `link-issues-by-milestone.yml` to automatically link issues to their "
    "parent roadmap item in `aind-scientific-computing` when assigned to a milestone. "
    "The milestone description should contain the URL of the parent roadmap issue."
)


def run(cmd, cwd=None):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def process_repo(gh, user_login, repo_name):
    print(f"\nProcessing {repo_name}...")
    try:
        upstream = gh.get_repo(f"{ORG}/{repo_name}")
    except GithubException as e:
        if e.status == 404:
            print(f"  Repo not found: {ORG}/{repo_name} — skipping.")
        else:
            print(f"  GitHub error on {repo_name}: {e}")
        return

    tmpdir = tempfile.mkdtemp()
    try:
        token = os.environ["GITHUB_TOKEN"]

        # Fork the upstream repo (no-op if fork already exists)
        fork = upstream.create_fork()
        print(f"  Fork ready: {fork.full_name}")
        time.sleep(3)  # GitHub forks are async; give it a moment

        # Clone the fork
        fork_url = fork.clone_url.replace("https://", f"https://{token}@")
        run(["git", "clone", "--depth=1", "--quiet", fork_url, tmpdir])

        # Create branch
        run(["git", "checkout", "-b", BRANCH], cwd=tmpdir)

        # Write workflow file
        workflow_dir = os.path.join(tmpdir, ".github", "workflows")
        os.makedirs(workflow_dir, exist_ok=True)
        with open(os.path.join(tmpdir, WORKFLOW_PATH), "w") as f:
            f.write(WORKFLOW_CONTENT)

        # Commit and push to fork
        run(["git", "add", WORKFLOW_PATH], cwd=tmpdir)
        run(["git", "commit", "-m", "Add ticket linking workflow"], cwd=tmpdir)
        run(["git", "push", "origin", BRANCH], cwd=tmpdir)

        # Open PR on upstream from fork branch
        pr = upstream.create_pull(
            title=PR_TITLE,
            body=PR_BODY,
            head=f"{user_login}:{BRANCH}",
            base=upstream.default_branch,
        )
        print(f"  PR opened: {pr.html_url}")

    except GithubException as e:
        print(f"  GitHub error on {repo_name}: {e}")
    except RuntimeError as e:
        print(f"  Git error on {repo_name}: {e}")
    finally:
        shutil.rmtree(tmpdir)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise EnvironmentError("Set GITHUB_TOKEN environment variable before running.")

    gh = Github(token)
    user_login = gh.get_user().login

    for repo_name in REPOS:
        process_repo(gh, user_login, repo_name)

    print("\nDone.")


if __name__ == "__main__":
    main()