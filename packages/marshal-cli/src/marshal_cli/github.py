import json
import sys
import urllib.error
import urllib.parse
import urllib.request

GITHUB_API = "https://api.github.com"
RED   = "\033[31m"
RESET = "\033[0m"


def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_issues_with_label(repo_full_name: str, label: str, token: str) -> list[dict]:
    """Return all open issues in repo that have the given label."""
    owner, repo = repo_full_name.split("/", 1)
    url = (
        f"{GITHUB_API}/repos/{owner}/{repo}/issues"
        f"?state=open&labels={urllib.parse.quote(label)}&per_page=100"
    )
    r = urllib.request.Request(url, headers=_gh_headers(token))
    try:
        with urllib.request.urlopen(r) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"{RED}GitHub API error {e.code}: {e.read().decode()[:200]}{RESET}")
        sys.exit(1)


def build_state(issue: dict, repo_full_name: str) -> dict:
    """Build initial_state from a GitHub issue object."""
    owner, repo = repo_full_name.split("/", 1)
    return {
        "github_issue": {
            "repo_owner":     owner,
            "repo_name":      repo,
            "repo_full_name": repo_full_name,
            "issue_number":   issue["number"],
            "title":          issue["title"],
            "body":           issue.get("body") or "",
            "url":            issue["html_url"],
            "author":         issue["user"]["login"],
            "labels":         [lb["name"] for lb in issue.get("labels", [])],
            "label_added":    next((lb["name"] for lb in issue.get("labels", [])), ""),
            "default_branch": "main",
            "clone_url":      f"https://github.com/{repo_full_name}.git",
        }
    }
