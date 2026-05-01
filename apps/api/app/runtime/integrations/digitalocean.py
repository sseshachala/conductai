"""
DigitalOcean integration — Droplets API v2.
Actions: create_droplet, get_droplet, destroy_droplet, wait_for_droplet, list_droplets.
"""
import time

import httpx

BASE = "https://api.digitalocean.com/v2"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_droplet(
    token: str,
    name: str,
    region: str = "nyc3",
    size: str = "s-1vcpu-1gb",
    image: str = "ubuntu-22-04-x64",
    tags: list | None = None,
    user_data: str | None = None,
) -> dict:
    payload: dict = {
        "name": name,
        "region": region,
        "size": size,
        "image": image,
        "tags": tags or ["marshal"],
    }
    if user_data:
        payload["user_data"] = user_data

    r = httpx.post(f"{BASE}/droplets", headers=_headers(token), json=payload, timeout=30)
    r.raise_for_status()
    d = r.json()["droplet"]
    return {
        "droplet_id": d["id"],
        "name": d["name"],
        "status": d["status"],
        "region": d["region"]["slug"],
        "size": d["size_slug"],
    }


def get_droplet(token: str, droplet_id: int) -> dict:
    r = httpx.get(f"{BASE}/droplets/{droplet_id}", headers=_headers(token), timeout=15)
    r.raise_for_status()
    d = r.json()["droplet"]
    networks = d.get("networks", {})
    ipv4 = next(
        (n["ip_address"] for n in networks.get("v4", []) if n["type"] == "public"),
        None,
    )
    return {
        "droplet_id": d["id"],
        "name": d["name"],
        "status": d["status"],
        "ip_address": ipv4,
        "region": d["region"]["slug"],
    }


def destroy_droplet(token: str, droplet_id: int) -> dict:
    r = httpx.delete(f"{BASE}/droplets/{droplet_id}", headers=_headers(token), timeout=15)
    if r.status_code == 404:
        return {"droplet_id": droplet_id, "destroyed": False, "reason": "not_found"}
    r.raise_for_status()
    return {"droplet_id": droplet_id, "destroyed": True}


def wait_for_droplet(token: str, droplet_id: int, timeout_seconds: int = 300) -> dict:
    """Poll until droplet status == 'active' or timeout."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        info = get_droplet(token=token, droplet_id=droplet_id)
        if info["status"] == "active" and info.get("ip_address"):
            return info
        time.sleep(10)
    raise TimeoutError(f"Droplet {droplet_id} did not become active within {timeout_seconds}s")


def list_droplets(token: str, tag: str | None = None) -> dict:
    params = {}
    if tag:
        params["tag_name"] = tag
    r = httpx.get(f"{BASE}/droplets", headers=_headers(token), params=params, timeout=15)
    r.raise_for_status()
    droplets = r.json()["droplets"]
    return {
        "droplets": [
            {"id": d["id"], "name": d["name"], "status": d["status"],
             "region": d["region"]["slug"]}
            for d in droplets
        ]
    }


TOOL_MAP = {
    "create_droplet": create_droplet,
    "get_droplet": get_droplet,
    "destroy_droplet": destroy_droplet,
    "wait_for_droplet": wait_for_droplet,
    "list_droplets": list_droplets,
}


def execute(action: str, params: dict, credentials: dict) -> dict:
    token = credentials.get("token") or credentials.get("api_key", "")
    fn = TOOL_MAP.get(action)
    if not fn:
        raise ValueError(f"Unknown DigitalOcean action: {action}")
    return fn(token=token, **params)
