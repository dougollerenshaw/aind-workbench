#!/usr/bin/env python3
"""
Backfill sub-issue links for issues that were milestoned before the linking
automation was deployed. Walks each repo in REPOS, finds milestoned issues
whose milestone description points at an aind-scientific-computing roadmap
issue, and (in --apply mode) registers them as sub-issues of that parent.

Dry-run by default. Pass --apply to actually create the links.
"""
import argparse
import os
import re
import sys
import requests

ORG = "AllenNeuralDynamics"
ROADMAP_REPO = "aind-scientific-computing"

REPOS = [
    "aind-behavior-utils",
    "aind-bonsai-behavior-nwb",
    "aind-dynamic-foraging-pipeline",
    "aind-dynamic-foraging-qc",
    "aind-ephys-ibl-gui-conversion",
    "aind-ephys-results-collector",
    "aind-fiber-photometry-pipeline",
    "aind-fiber-photometry-standalone-pipeline",
    "aind-file-standards",
    "aind-fip-dff",
    "aind-fip-nwb-base-capsule",
    "aind-fip-qc-raw",
    "aind-log-utils",
    "aind-metadata-manager",
    "aind-metadata-mapper",
    "aind-nwb-utils",
    "aind-ophys-camstim-behavior-qc",
    "aind-ophys-classifier",
    "aind-ophys-motion-correction",
    "aind-ophys-movie-qc",
    "aind-ophys-nwb",
    "aind-pavlovian-behavior-capsule",
    "aind-physio-arch",
    "aind-pophys-converter",
    "aind-pophys-converter-capsule",
    "aind-pophys-pipeline",
    "aind-running-speed-nwb",
    "aind-scientific-computing",
    "aind-vr-foraging-pipeline",
    "aind-vr-foraging-processing-nwb-packaging",
    "isi_segmentation",
]

ROADMAP_URL_PATTERN = re.compile(
    rf"https?://github\.com/{ORG}/{ROADMAP_REPO}/issues/(\d+)"
)


def make_session(token):
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Accept": "application/vnd.github+json",
    })
    return s


def list_milestoned_issues(session, repo_name):
    """List all issues (open + closed) in a repo that have a milestone assigned."""
    issues = []
    page = 1
    while True:
        resp = session.get(
            f"https://api.github.com/repos/{ORG}/{repo_name}/issues",
            params={"state": "all", "per_page": 100, "page": page},
        )
        if resp.status_code == 404:
            print(f"  Repo not found: {repo_name}")
            return []
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for issue in batch:
            # Skip pull requests (the issues endpoint includes them)
            if "pull_request" in issue:
                continue
            if issue.get("milestone"):
                issues.append(issue)
        page += 1
    return issues


def parse_parent_number(milestone_description):
    if not milestone_description:
        return None
    match = ROADMAP_URL_PATTERN.search(milestone_description)
    return int(match.group(1)) if match else None


def get_existing_sub_issue_ids(session, parent_number):
    """Return set of integer IDs of existing sub-issues on the parent."""
    ids = set()
    page = 1
    while True:
        resp = session.get(
            f"https://api.github.com/repos/{ORG}/{ROADMAP_REPO}/issues/{parent_number}/sub_issues",
            params={"per_page": 100, "page": page},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for si in batch:
            ids.add(si["id"])
        page += 1
    return ids


def add_sub_issue(session, parent_number, child_id):
    resp = session.post(
        f"https://api.github.com/repos/{ORG}/{ROADMAP_REPO}/issues/{parent_number}/sub_issues",
        json={"sub_issue_id": child_id},
    )
    if not resp.ok:
        raise RuntimeError(f"Failed to add sub-issue {child_id} to #{parent_number}: {resp.status_code} {resp.text}")
    return resp.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Actually create sub-issue links. Default is dry-run.")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    session = make_session(token)

    # Step 1: collect candidate links: (parent_number, child_id, child_number, child_repo, child_title)
    candidates = []
    print("Scanning repos for milestoned issues with roadmap URLs...\n")

    for repo_name in REPOS:
        issues = list_milestoned_issues(session, repo_name)
        repo_lines = []
        for issue in issues:
            milestone = issue["milestone"]
            parent_number = parse_parent_number(milestone.get("description"))
            if parent_number is None:
                continue
            # Guard: skip self-links (issue would become its own sub-issue)
            if repo_name == ROADMAP_REPO and issue["number"] == parent_number:
                repo_lines.append(f"  SKIP self-link: #{issue['number']} would be sub-issue of itself")
                continue
            candidates.append({
                "parent_number": parent_number,
                "child_id": issue["id"],
                "child_number": issue["number"],
                "child_repo": repo_name,
                "child_title": issue["title"],
                "milestone_title": milestone["title"],
            })
            repo_lines.append(f"  #{issue['number']} ({issue['state']}) — milestone '{milestone['title']}' → roadmap #{parent_number}")
        if repo_lines:
            print(f"=== {repo_name} ===")
            for line in repo_lines:
                print(line)

    if not candidates:
        print("\nNo candidates found.")
        return

    # Step 2: for each unique parent, check existing sub-issues and link new ones
    print(f"\n\nFound {len(candidates)} candidate links across {len(set(c['parent_number'] for c in candidates))} parent issues.")
    print(f"\n{'APPLYING' if args.apply else 'DRY RUN — pass --apply to actually link'}\n")

    parent_existing_subs = {}
    to_link = []
    for c in candidates:
        pn = c["parent_number"]
        if pn not in parent_existing_subs:
            try:
                parent_existing_subs[pn] = get_existing_sub_issue_ids(session, pn)
            except requests.HTTPError as e:
                print(f"  Couldn't read existing sub-issues on #{pn}: {e}")
                parent_existing_subs[pn] = set()
        if c["child_id"] in parent_existing_subs[pn]:
            print(f"  ALREADY LINKED: {c['child_repo']}#{c['child_number']} → roadmap #{pn}")
        else:
            to_link.append(c)
            print(f"  WILL LINK: {c['child_repo']}#{c['child_number']} ({c['child_title']!r}) → roadmap #{pn}")

    if not to_link:
        print("\nNothing to do — all candidates are already linked.")
        return

    if not args.apply:
        print(f"\n{len(to_link)} link(s) would be created. Re-run with --apply.")
        return

    print(f"\nApplying {len(to_link)} link(s)...")
    for c in to_link:
        try:
            add_sub_issue(session, c["parent_number"], c["child_id"])
            print(f"  linked {c['child_repo']}#{c['child_number']} → roadmap #{c['parent_number']}")
        except RuntimeError as e:
            print(f"  FAILED: {e}")


if __name__ == "__main__":
    main()
