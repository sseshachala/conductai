"""
Slack integration — tool implementations.
"""
import httpx

BASE = "https://slack.com/api"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def post_message(token: str, channel: str, text: str, blocks: list | None = None) -> dict:
    payload: dict = {"channel": channel, "text": text}
    if blocks:
        payload["blocks"] = blocks
    r = httpx.post(f"{BASE}/chat.postMessage", headers=_headers(token), json=payload, timeout=15)
    r.raise_for_status()
    d = r.json()
    if not d.get("ok"):
        raise ValueError(f"Slack error: {d.get('error')}")
    return {"ts": d["ts"], "channel": d["channel"], "text": text}


def post_dm(token: str, user: str, text: str) -> dict:
    # Open DM channel
    r = httpx.post(f"{BASE}/conversations.open", headers=_headers(token), json={"users": user}, timeout=15)
    r.raise_for_status()
    channel_id = r.json()["channel"]["id"]
    return post_message(token=token, channel=channel_id, text=text)


def post_approval_message(token: str, channel: str, text: str, run_id: str, callback_url: str) -> dict:
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "value": f"approve:{run_id}",
                    "action_id": "approve_run",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "style": "danger",
                    "value": f"reject:{run_id}",
                    "action_id": "reject_run",
                },
            ],
        },
    ]
    return post_message(token=token, channel=channel, text=text, blocks=blocks)


TOOL_MAP = {
    "post_message": post_message,
    "post_dm": post_dm,
    "post_approval_message": post_approval_message,
}


def execute(action: str, params: dict, credentials: dict) -> dict:
    token = credentials.get("token") or credentials.get("bot_token", "")
    fn = TOOL_MAP.get(action)
    if not fn:
        raise ValueError(f"Unknown Slack action: {action}")
    return fn(token=token, **params)
