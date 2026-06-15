"""
GitHub integration — tool implementations.
Each function takes a params dict and returns a structured result dict.
"""
import httpx

BASE = "https://api.github.com"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_issue(token: str, owner: str, repo: str, issue_number: int) -> dict:
    r = httpx.get(f"{BASE}/repos/{owner}/{repo}/issues/{issue_number}", headers=_headers(token), timeout=15)
    r.raise_for_status()
    d = r.json()
    return {
        "issue_number": d["number"],
        "title": d["title"],
        "body": d.get("body") or "",
        "state": d["state"],
        "url": d["html_url"],
        "owner": owner,
        "repo": repo,
        "labels": [l["name"] for l in d.get("labels", [])],
        "author": d["user"]["login"],
    }


def list_issues(token: str, owner: str, repo: str, label: str = "", state: str = "open") -> dict:
    params: dict = {"state": state, "per_page": 20}
    if label:
        params["labels"] = label
    r = httpx.get(f"{BASE}/repos/{owner}/{repo}/issues", headers=_headers(token), params=params, timeout=15)
    r.raise_for_status()
    issues = [
        {"number": i["number"], "title": i["title"], "url": i["html_url"],
         "labels": [l["name"] for l in i.get("labels", [])]}
        for i in r.json()
        if "pull_request" not in i
    ]
    return {"issues": issues, "count": len(issues)}


def get_repo(token: str, owner: str, repo: str) -> dict:
    r = httpx.get(f"{BASE}/repos/{owner}/{repo}", headers=_headers(token), timeout=15)
    r.raise_for_status()
    d = r.json()
    is_fork = bool(d.get("fork"))
    parent = d.get("parent") or {}
    parent_full = parent.get("full_name", d["full_name"])
    parent_owner, _, parent_repo = parent_full.partition("/")
    return {
        "full_name": d["full_name"],
        "default_branch": d["default_branch"],
        "clone_url": d["clone_url"],
        "is_fork": is_fork,
        "parent_full_name": parent_full,
        "parent_owner": parent_owner,
        "parent_repo": parent_repo,
        # pr_target_* = upstream if fork, self if not
        "pr_target_full_name": parent_full if is_fork else d["full_name"],
        "pr_target_owner": parent_owner if is_fork else owner,
        "pr_target_repo": parent_repo if is_fork else repo,
        "pr_head_prefix": f"{owner}:" if is_fork else "",
    }


def create_branch(token: str, owner: str, repo: str, branch: str, from_branch: str = "main") -> dict:
    # Get SHA of base branch
    r = httpx.get(f"{BASE}/repos/{owner}/{repo}/git/ref/heads/{from_branch}", headers=_headers(token), timeout=15)
    r.raise_for_status()
    sha = r.json()["object"]["sha"]

    # Create new branch
    r2 = httpx.post(
        f"{BASE}/repos/{owner}/{repo}/git/refs",
        headers=_headers(token),
        json={"ref": f"refs/heads/{branch}", "sha": sha},
        timeout=15,
    )
    if r2.status_code == 422:
        return {"branch": branch, "sha": sha, "already_exists": True}
    r2.raise_for_status()
    return {"branch": branch, "sha": sha, "already_exists": False}


def open_pull_request(token: str, owner: str, repo: str, title: str, head: str, base: str, body: str = "") -> dict:
    # Verify head branch exists before attempting PR creation
    branch_name = head.split(":")[-1]
    branch_owner = head.split(":")[0] if ":" in head else owner
    branch_check = httpx.get(
        f"{BASE}/repos/{branch_owner}/{repo}/branches/{branch_name}",
        headers=_headers(token),
        timeout=10,
    )
    if branch_check.status_code == 404:
        raise ValueError(
            f"Branch '{head}' not found on {branch_owner}/{repo}. "
            "The push likely failed — check that the brain block pushed the branch successfully before opening a PR."
        )

    r = httpx.post(
        f"{BASE}/repos/{owner}/{repo}/pulls",
        headers=_headers(token),
        json={"title": title, "head": head, "base": base, "body": body, "draft": True},
        timeout=15,
    )
    if r.status_code == 422:
        errors = r.json().get("errors", [])
        # PR already exists — find it and return it instead of failing
        if any("already exists" in str(e) for e in errors):
            existing = httpx.get(
                f"{BASE}/repos/{owner}/{repo}/pulls",
                headers=_headers(token),
                params={"head": head, "base": base, "state": "open"},
                timeout=10,
            )
            if existing.status_code == 200 and existing.json():
                d = existing.json()[0]
                return {"pr_number": d["number"], "pr_url": d["html_url"], "title": d["title"]}
        msg = "; ".join(e.get("message", str(e)) for e in errors) if errors else r.text
        raise ValueError(f"GitHub rejected PR creation (422): {msg}")
    r.raise_for_status()
    d = r.json()
    return {"pr_number": d["number"], "pr_url": d["html_url"], "title": d["title"]}


def list_pull_requests(token: str, owner: str, repo: str, state: str = "open") -> dict:
    r = httpx.get(
        f"{BASE}/repos/{owner}/{repo}/pulls",
        headers=_headers(token),
        params={"state": state, "per_page": 10},
        timeout=15,
    )
    r.raise_for_status()
    prs = [{"number": p["number"], "title": p["title"], "url": p["html_url"]} for p in r.json()]
    return {"pull_requests": prs}


def create_repo(
    token: str,
    name: str,
    description: str = "",
    private: bool = True,
    auto_init: bool = True,
) -> dict:
    r = httpx.post(
        f"{BASE}/user/repos",
        headers=_headers(token),
        json={
            "name": name,
            "description": description,
            "private": private,
            "auto_init": auto_init,
        },
        timeout=15,
    )
    if r.status_code == 422:
        # Repo already exists — fetch it instead
        user_r = httpx.get(f"{BASE}/user", headers=_headers(token), timeout=10)
        user_r.raise_for_status()
        owner = user_r.json()["login"]
        return get_repo(token=token, owner=owner, repo=name)
    r.raise_for_status()
    d = r.json()
    return {
        "full_name": d["full_name"],
        "clone_url": d["clone_url"],
        "ssh_url": d["ssh_url"],
        "html_url": d["html_url"],
        "private": d["private"],
        "default_branch": d.get("default_branch", "main"),
    }


def read_file(token: str, owner: str, repo: str, path: str, ref: str | None = None) -> dict:
    """
    Read a single file from a repo and return its decoded text contents.

    Used primarily by the workflow repo-sync flow (``delegator.yml`` lives
    in the customer's repo). Falls back gracefully when the file is missing —
    callers that need a sync-failure signal should check ``found``.
    """
    import base64

    params: dict = {}
    if ref:
        params["ref"] = ref
    r = httpx.get(
        f"{BASE}/repos/{owner}/{repo}/contents/{path}",
        headers=_headers(token),
        params=params,
        timeout=15,
    )
    if r.status_code == 404:
        return {"found": False, "path": path, "ref": ref}
    r.raise_for_status()
    d = r.json()
    if isinstance(d, list):
        # GitHub returns a list when ``path`` is a directory. We only support files.
        return {"found": False, "path": path, "ref": ref, "reason": "path is a directory"}

    content = d.get("content") or ""
    encoding = d.get("encoding")
    if encoding == "base64":
        try:
            text = base64.b64decode(content).decode("utf-8")
        except Exception as e:
            return {"found": True, "path": path, "ref": ref, "error": f"decode failed: {e}"}
    else:
        text = content

    return {
        "found": True,
        "path": d.get("path"),
        "ref": ref,
        "sha": d.get("sha"),
        "size": d.get("size"),
        "content": text,
    }


def fork_repo(token: str, owner: str, repo: str) -> dict:
    """Fork a repo into the authenticated user's account and return fork metadata.

    Handles all three cases generically:
    1. Proper fork already exists → return it, no API call needed
    2. No repo with that name exists → fork with original name
    3. Non-fork repo with same name exists → fork with '{repo}-fork' suffix
    """
    import time

    user_r = httpx.get(f"{BASE}/user", headers=_headers(token), timeout=10)
    user_r.raise_for_status()
    fork_owner = user_r.json()["login"]

    # Case 1: proper fork already exists — reuse it
    existing = httpx.get(f"{BASE}/repos/{fork_owner}/{repo}", headers=_headers(token), timeout=10)
    if existing.status_code == 200 and existing.json().get("fork"):
        d = existing.json()
        return {
            "fork_owner": fork_owner,
            "fork_name": repo,
            "fork_full_name": f"{fork_owner}/{repo}",
            "default_branch": d.get("default_branch", "main"),
            "html_url": d.get("html_url", f"https://github.com/{fork_owner}/{repo}"),
            "already_existed": True,
        }

    # Case 3: non-fork name conflict → use '{repo}-fork'
    fork_name = repo
    if existing.status_code == 200 and not existing.json().get("fork"):
        fork_name = f"{repo}-fork"

    # Cases 2 & 3: create the fork
    payload = {"name": fork_name} if fork_name != repo else {}
    r = httpx.post(f"{BASE}/repos/{owner}/{repo}/forks", headers=_headers(token), json=payload, timeout=30)
    r.raise_for_status()
    d = r.json()

    # Fork creation is async — poll until reachable and confirmed as a fork (max 30s)
    for _ in range(10):
        time.sleep(3)
        check = httpx.get(f"{BASE}/repos/{fork_owner}/{fork_name}", headers=_headers(token), timeout=10)
        if check.status_code == 200 and check.json().get("fork"):
            break

    return {
        "fork_owner": fork_owner,
        "fork_name": fork_name,
        "fork_full_name": f"{fork_owner}/{fork_name}",
        "default_branch": d.get("default_branch", "main"),
        "html_url": d.get("html_url", f"https://github.com/{fork_owner}/{fork_name}"),
        "already_existed": False,
    }


def update_file(
    token: str,
    owner: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str,
    sha: str = "",
) -> dict:
    """Create or update a single file in a repo (one commit per call)."""
    import base64

    encoded = base64.b64encode(content.encode("utf-8")).decode()
    payload: dict = {"message": message, "content": encoded, "branch": branch}
    if sha:
        payload["sha"] = sha

    r = httpx.put(
        f"{BASE}/repos/{owner}/{repo}/contents/{path}",
        headers=_headers(token),
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    return {
        "path": path,
        "commit_sha": d["commit"]["sha"],
        "branch": branch,
        "url": d["content"]["html_url"],
    }


def add_repo_secret(token: str, owner: str, repo: str, secret_name: str, secret_value: str) -> dict:
    """Add or update a GitHub Actions secret in a repo (requires nacl for encryption)."""
    try:
        from base64 import b64encode
        from nacl import encoding, public  # type: ignore[import]

        # Get repo public key
        pk_r = httpx.get(f"{BASE}/repos/{owner}/{repo}/actions/secrets/public-key", headers=_headers(token), timeout=10)
        pk_r.raise_for_status()
        pk_data = pk_r.json()
        pub_key = public.PublicKey(pk_data["key"].encode(), encoding.Base64Encoder())
        sealed = public.SealedBox(pub_key).encrypt(secret_value.encode())
        encrypted = b64encode(sealed).decode()

        r = httpx.put(
            f"{BASE}/repos/{owner}/{repo}/actions/secrets/{secret_name}",
            headers=_headers(token),
            json={"encrypted_value": encrypted, "key_id": pk_data["key_id"]},
            timeout=15,
        )
        r.raise_for_status()
        return {"secret": secret_name, "repo": f"{owner}/{repo}", "set": True}
    except ImportError:
        return {"secret": secret_name, "repo": f"{owner}/{repo}", "set": False, "reason": "PyNaCl not installed on server"}


def search_code(token: str, query: str, per_page: int = 10) -> dict:
    """Search code across GitHub repos. Returns file paths matching the query.

    Falls back to the Git Trees API when the Code Search API returns 0 results
    or an unresolved template ref slips through as the keyword.
    """
    import re as _re

    _empty = {"total_count": 0, "items": [], "paths": []}

    # Bail early if the query contains an unresolved template placeholder
    # (e.g. plan_fix JSON was truncated and grep_pattern never landed in state).
    if _re.search(r"\{\{[\w.]+\}\}", query):
        return {**_empty, "error": f"unresolved_template: {query}"}

    # Extract the repo qualifier so we can fall back to Trees API.
    repo_match = _re.search(r"repo:([\w.\-]+/[\w.\-]+)", query)
    repo_full = repo_match.group(1) if repo_match else None

    # Strip the keyword (everything before the first qualifier).
    keyword = _re.sub(r"\s+\w+:[^\s]+", "", query).strip()

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # ── 1. Try GitHub Code Search ─────────────────────────────────────────────
    if keyword:
        try:
            r = httpx.get(
                "https://api.github.com/search/code",
                headers=headers,
                params={"q": query, "per_page": min(per_page, 30)},
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json()
                items = [
                    {
                        "path": item["path"],
                        "repo": item["repository"]["full_name"],
                        "url": item["html_url"],
                        "sha": item["sha"],
                    }
                    for item in data.get("items", [])
                ]
                if items:
                    return {
                        "total_count": data.get("total_count", 0),
                        "items": items,
                        "paths": [i["path"] for i in items],
                    }
            # 422 = invalid query, 403 = rate-limited — fall through to Trees
        except Exception:
            pass

    # ── 2. Fallback: scan repo file tree for paths containing the keyword ─────
    if not repo_full or not keyword:
        return _empty

    try:
        # Resolve default branch HEAD SHA
        r2 = httpx.get(
            f"https://api.github.com/repos/{repo_full}/git/trees/HEAD",
            headers=headers,
            params={"recursive": "1"},
            timeout=20,
        )
        if r2.status_code != 200:
            return _empty
        tree = r2.json().get("tree", [])
        kw_lower = keyword.lower()
        matched = [
            {"path": node["path"], "repo": repo_full, "url": "", "sha": node.get("sha", "")}
            for node in tree
            if node.get("type") == "blob" and kw_lower in node["path"].lower()
        ][:per_page]
        return {
            "total_count": len(matched),
            "items": matched,
            "paths": [m["path"] for m in matched],
            "source": "trees_fallback",
        }
    except Exception:
        return _empty


def create_issue(token: str, repo: str, title: str, body: str = "", labels: list | None = None, owner: str = "") -> dict:
    if "/" in repo:
        owner, repo = repo.split("/", 1)
    r = httpx.post(
        f"{BASE}/repos/{owner}/{repo}/issues",
        headers=_headers(token),
        json={"title": title, "body": body, "labels": labels or []},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    return {"issue_url": d.get("html_url", ""), "issue_number": d.get("number")}


TOOL_MAP = {
    "fetch_issue": fetch_issue,
    "list_issues": list_issues,
    "get_repo": get_repo,
    "create_branch": create_branch,
    "open_pull_request": open_pull_request,
    "list_pull_requests": list_pull_requests,
    "create_repo": create_repo,
    "add_repo_secret": add_repo_secret,
    "read_file": read_file,
    "fork_repo": fork_repo,
    "update_file": update_file,
    "search_code": search_code,
    "create_issue": create_issue,
}


def execute(action: str, params: dict, credentials: dict) -> dict:
    token = credentials.get("token") or credentials.get("api_key", "")
    fn = TOOL_MAP.get(action)
    if not fn:
        raise ValueError(f"Unknown GitHub action: {action}")
    return fn(token=token, **params)
