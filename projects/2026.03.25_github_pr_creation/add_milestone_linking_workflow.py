#!/usr/bin/env python3
"""
Update existing link-issues-by-milestone.yml workflows to use the
reusable workflow from AllenNeuralDynamics/.github.
"""
import os
import subprocess
import tempfile
import shutil
import time
from github import Github, GithubException

WORKFLOW_CONTENT = """\
name: Link Issue to Milestone Parent

on:
  issues:
    types: [milestoned]

jobs:
  link-issue:
    if: github.event.issue.milestone != null
    uses: AllenNeuralDynamics/.github/.github/workflows/util-link-issues-by-milestone.yml@main
    with:
      issue-number: ${{ github.event.issue.number }}
      issue-id: ${{ github.event.issue.id }}
      milestone-description: ${{ github.event.issue.milestone.description }}
    secrets:
      service-token: ${{ secrets.SERVICE_TOKEN }}
"""

# REPOS = [
    # "aind-data-schema",
    # "aind-data-schema-models",
    # "aind-metadata-upgrader",
    # "aind-metadata-utils",
    # "aind-metadata-viz",
    # "aind-metadata-validator",
    # "aind-qc-portal",
    # "aind-qcportal-schema",
    # "zombie",
    # "zombie-squirrel",
    # "aind-software-docs",
    # "aind-data-mcp",
#     "milestone-testing",
# ]

REPOS = [
    "aind-fiber-photometry-pipeline"
]

ORG = "AllenNeuralDynamics"
BRANCH = "feat-add-milestone-linking-workflow"
WORKFLOW_PATH = ".github/workflows/link-issues-by-milestone.yml"
PR_TITLE = "Add milestone-based issue linking workflow from reusable workflow"
PR_BODY = (
    "Adds `link-issues-by-milestone.yml` which calls the shared reusable workflow "
    "from `AllenNeuralDynamics/.github` to automatically link milestoned issues "
    "as sub-issues of their parent roadmap item in `aind-scientific-computing`.\n\n"
    "See: https://github.com/AllenNeuralDynamics/.github/commit/2e9002effcd15196c5d05a5f7252315c331f6748"
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

    # Skip if an open PR with our branch name already exists
    try:
        for pr in upstream.get_pulls(state="open"):
            if pr.head.ref == BRANCH:
                print(f"  Open PR already exists: {pr.html_url} — skipping.")
                return
    except GithubException as e:
        print(f"  Couldn't check existing PRs on {repo_name}: {e}")
        return

    tmpdir = tempfile.mkdtemp()
    try:
        token = os.environ["GITHUB_TOKEN"]
        clone_url = upstream.clone_url.replace("https://", f"https://{token}@")
        run(["git", "clone", "--depth=1", "--quiet", clone_url, tmpdir])

        # Create branch
        run(["git", "checkout", "-b", BRANCH], cwd=tmpdir)

        # Write workflow file (overwrites existing)
        workflow_dir = os.path.join(tmpdir, ".github", "workflows")
        os.makedirs(workflow_dir, exist_ok=True)
        with open(os.path.join(tmpdir, WORKFLOW_PATH), "w") as f:
            f.write(WORKFLOW_CONTENT)

        # Check if there's actually a diff
        diff = subprocess.run(
            ["git", "diff", "--name-only"], cwd=tmpdir, capture_output=True, text=True
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=tmpdir, capture_output=True, text=True
        )
        if not diff.stdout.strip() and not status.stdout.strip():
            print(f"  No changes needed for {repo_name} — already up to date.")
            return

        # Commit
        run(["git", "add", WORKFLOW_PATH], cwd=tmpdir)
        run(["git", "commit", "-m", "Add milestone-based issue linking workflow"], cwd=tmpdir)

        # Try direct push; fall back to fork if no write access
        use_fork = False
        try:
            run(["git", "push", "origin", BRANCH], cwd=tmpdir)
            print(f"  Pushed branch directly to {ORG}/{repo_name}")
        except RuntimeError:
            print(f"  No write access — trying fork...")
            fork = upstream.create_fork()
            print(f"  Fork ready: {fork.full_name}")
            time.sleep(3)
            fork_url = fork.clone_url.replace("https://", f"https://{token}@")
            run(["git", "remote", "set-url", "origin", fork_url], cwd=tmpdir)
            run(["git", "push", "origin", BRANCH], cwd=tmpdir)
            use_fork = True

        # Open PR
        head = f"{user_login}:{BRANCH}" if use_fork else BRANCH
        pr = upstream.create_pull(
            title=PR_TITLE,
            body=PR_BODY,
            head=head,
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
