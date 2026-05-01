"""
Linear integration — GraphQL API v2.
Actions: fetch_issue, list_issues, create_comment, update_issue_status, create_issue.
"""
import httpx

GQL_URL = "https://api.linear.app/graphql"


def _headers(api_key: str) -> dict:
    return {"Authorization": api_key, "Content-Type": "application/json"}


def _gql(api_key: str, query: str, variables: dict | None = None) -> dict:
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables
    r = httpx.post(GQL_URL, headers=_headers(api_key), json=payload, timeout=20)
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise ValueError(f"Linear GraphQL error: {body['errors']}")
    return body.get("data", {})


def fetch_issue(api_key: str, issue_id: str) -> dict:
    data = _gql(api_key, """
        query($id: String!) {
          issue(id: $id) {
            id identifier title description
            state { name }
            assignee { name email }
            labels { nodes { name } }
            url
          }
        }
    """, {"id": issue_id})
    issue = data.get("issue", {})
    return {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "description": issue.get("description"),
        "state": issue.get("state", {}).get("name"),
        "assignee": issue.get("assignee", {}).get("name") if issue.get("assignee") else None,
        "labels": [l["name"] for l in issue.get("labels", {}).get("nodes", [])],
        "url": issue.get("url"),
    }


def list_issues(api_key: str, team_id: str, label: str | None = None, limit: int = 20) -> dict:
    filter_clause = 'filter: { team: { id: { eq: $teamId } } }'
    data = _gql(api_key, f"""
        query($teamId: String!) {{
          issues({filter_clause}, first: {limit}, orderBy: updatedAt) {{
            nodes {{
              id identifier title state {{ name }} url
              labels {{ nodes {{ name }} }}
            }}
          }}
        }}
    """, {"teamId": team_id})
    issues = data.get("issues", {}).get("nodes", [])
    if label:
        issues = [i for i in issues if label in [l["name"] for l in i.get("labels", {}).get("nodes", [])]]
    return {"issues": [
        {"id": i["id"], "identifier": i["identifier"], "title": i["title"],
         "state": i["state"]["name"], "url": i["url"]}
        for i in issues
    ]}


def create_comment(api_key: str, issue_id: str, body: str) -> dict:
    data = _gql(api_key, """
        mutation($issueId: String!, $body: String!) {
          commentCreate(input: { issueId: $issueId, body: $body }) {
            success
            comment { id url }
          }
        }
    """, {"issueId": issue_id, "body": body})
    result = data.get("commentCreate", {})
    return {"success": result.get("success"), "comment_id": result.get("comment", {}).get("id")}


def update_issue_status(api_key: str, issue_id: str, state_id: str) -> dict:
    data = _gql(api_key, """
        mutation($id: String!, $stateId: String!) {
          issueUpdate(id: $id, input: { stateId: $stateId }) {
            success
            issue { id identifier state { name } }
          }
        }
    """, {"id": issue_id, "stateId": state_id})
    result = data.get("issueUpdate", {})
    return {
        "success": result.get("success"),
        "state": result.get("issue", {}).get("state", {}).get("name"),
    }


def create_issue(api_key: str, team_id: str, title: str, description: str = "", label_ids: list | None = None) -> dict:
    variables: dict = {"teamId": team_id, "title": title, "description": description}
    if label_ids:
        variables["labelIds"] = label_ids
    data = _gql(api_key, """
        mutation($teamId: String!, $title: String!, $description: String, $labelIds: [String!]) {
          issueCreate(input: { teamId: $teamId, title: $title, description: $description, labelIds: $labelIds }) {
            success
            issue { id identifier url }
          }
        }
    """, variables)
    result = data.get("issueCreate", {})
    return {
        "success": result.get("success"),
        "id": result.get("issue", {}).get("id"),
        "identifier": result.get("issue", {}).get("identifier"),
        "url": result.get("issue", {}).get("url"),
    }


TOOL_MAP = {
    "fetch_issue": fetch_issue,
    "list_issues": list_issues,
    "create_comment": create_comment,
    "update_issue_status": update_issue_status,
    "create_issue": create_issue,
}


def execute(action: str, params: dict, credentials: dict) -> dict:
    api_key = credentials.get("api_key") or credentials.get("token", "")
    fn = TOOL_MAP.get(action)
    if not fn:
        raise ValueError(f"Unknown Linear action: {action}")
    return fn(api_key=api_key, **params)
