import os
from github import Github

token = os.environ.get("GITHUB_TOKEN")
if not token:
    print("GITHUB_TOKEN is not set.")
else:
    gh = Github(token)
    user = gh.get_user()
    print(f"Token found. Authenticated as: {user.login}")
