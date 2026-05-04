#!/usr/bin/env python3
"""
Read-only check: for each repo in REPOS, report whether the authenticated user
has push access and whether forking is enabled. Flag repos where neither path
is available, since the PR script can't proceed on those.
"""
import os
from github import Github, GithubException

ORG = "AllenNeuralDynamics"

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


def main():
    token = os.environ["GITHUB_TOKEN"]
    gh = Github(token)

    blocked = []
    forking_disabled = []
    no_push = []
    ok = []
    not_found = []

    for repo_name in REPOS:
        try:
            repo = gh.get_repo(f"{ORG}/{repo_name}")
        except GithubException as e:
            if e.status == 404:
                not_found.append(repo_name)
                print(f"  ✗ {repo_name}: not found")
            else:
                print(f"  ? {repo_name}: error {e.status}")
            continue

        perms = repo.permissions
        can_push = perms.push if perms else False
        can_fork = repo.allow_forking

        status = []
        if can_push:
            status.append("push: YES")
        else:
            status.append("push: no")
            no_push.append(repo_name)
        if can_fork:
            status.append("fork: YES")
        else:
            status.append("fork: no")
            forking_disabled.append(repo_name)

        if not can_push and not can_fork:
            blocked.append(repo_name)
            verdict = "NEEDS FIXED"
        else:
            ok.append(repo_name)
            verdict = "GOOD"

        print(f"  {repo_name}: {', '.join(status)} — {verdict}")

    print("\n" + "=" * 60)
    print(f"Total: {len(REPOS)} repos")
    print(f"  Will work: {len(ok)}")
    print(f"  Blocked (no push AND no fork): {len(blocked)}")
    print(f"  Not found: {len(not_found)}")

    if blocked:
        print("\n=== Blocked repos (Arielle needs to enable forking or grant write access) ===")
        for r in blocked:
            print(f"  https://github.com/{ORG}/{r}")

    if forking_disabled:
        print(f"\n=== All repos with forking disabled ({len(forking_disabled)}) ===")
        for r in forking_disabled:
            print(f"  {r}")


if __name__ == "__main__":
    main()
