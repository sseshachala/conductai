"""
Slack integration — tool implementations.
"""
import httpx

BASE = "https://slack.com/api"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _bot_name(token: str) -> str:
    try:
        r = httpx.post(f"{BASE}/auth.test", headers=_headers(token), timeout=10)
        d = r.json()
        return d.get("bot_id") and d.get("user", "the bot") or "the bot"
    except Exception:
        return "the bot"


def _ensure_in_channel(token: str, channel: str) -> None:
    """Attempt to join a public channel. Silently skips private channels."""
    try:
        r = httpx.post(
            f"{BASE}/conversations.join",
            headers=_headers(token),
            json={"channel": channel},
            timeout=10,
        )
        d = r.json()
        # method_not_supported_for_channel_type = private channel — can't auto-join
        if not d.get("ok") and d.get("error") not in ("method_not_supported_for_channel_type", "already_in_channel"):
            pass  # non-fatal — postMessage will surface the real error
    except Exception:
        pass


def post_message(token: str, channel: str, text: str, blocks: list | None = None) -> dict:
    _ensure_in_channel(token, channel)
    payload: dict = {"channel": channel, "text": text}
    if blocks:
        payload["blocks"] = blocks
    r = httpx.post(f"{BASE}/chat.postMessage", headers=_headers(token), json=payload, timeout=15)
    r.raise_for_status()
    d = r.json()
    if not d.get("ok"):
        err = d.get("error", "unknown")
        if err == "not_in_channel":
            bot = _bot_name(token)
            raise ValueError(
                f"Slack error: bot is not in {channel}. "
                f"Run /invite @{bot} in that channel, or use a public channel."
            )
        raise ValueError(f"Slack error: {err}")
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
