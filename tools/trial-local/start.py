"""Launch an isolated local trial API using the existing security-E2E fixtures.

Credentials are passed to Docker through stdin, never printed or written to disk.
"""
import json
import base64
import os
import sys
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
name = "conduct-trial-local-api"


def docker(*args, **kwargs):
    return subprocess.run(["rtk", "docker", *args], check=True, **kwargs)


# Raw JSON is needed here, so bypass RTK's display filter.
source = json.loads(subprocess.check_output([
    "rtk", "proxy", "docker", "inspect", "conduct-e2e-api-1",
], text=True))[0]
existing = dict(value.split("=", 1) for value in source["Config"]["Env"])
allowed = ("DATABASE_URL", "REDIS_URL", "ENCRYPTION_KEY", "CLERK_SECRET_KEY", "CLERK_FRONTEND_API", "CLERK_AUDIENCE")
env = {key: existing[key] for key in allowed if key in existing}
if not env.get("CLERK_SECRET_KEY", "").startswith("sk_test_"):
    raise SystemExit("Refusing non-test Clerk credentials")
if "@postgres/conduct_e2e" not in env.get("DATABASE_URL", ""):
    raise SystemExit("Refusing a non-local database")
if sys.argv[1:] == ["--web-only"]:
    frontend = env.get("CLERK_FRONTEND_API", "")
    if not frontend.endswith(".accounts.dev"):
        raise SystemExit("Refusing a non-test Clerk frontend")
    web_env = {
        **os.environ,
        "CLERK_SECRET_KEY": env["CLERK_SECRET_KEY"],
        "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY": "pk_test_" + base64.b64encode((frontend + "$").encode()).decode().rstrip("="),
        "NEXT_PUBLIC_API_URL": "http://localhost:3110",
    }
    os.chdir(root / "apps/web")
    os.execvpe("rtk", ["rtk", "proxy", "npm", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3107"], web_env)
env.update({
    "ENVIRONMENT": "development",
    "APP_URL": "http://localhost:3107",
    "CONDUCT_WEB_URL": "http://localhost:3107",
    "ALLOWED_ORIGINS": "http://localhost:3107",
    "API_BASE_URL": "http://localhost:3110",
    "CONDUCT_PROXY_URL": "http://localhost:3110/gateway/v1",
})
if any("\n" in value for value in env.values()):
    raise SystemExit("Invalid multiline environment value")
networks = source["NetworkSettings"]["Networks"]
data = next(n for n in networks if n.endswith("_data"))
edge = next(n for n in networks if n.endswith("_edge"))
docker("create", "--name", name, "--network", data,
       "--publish", "127.0.0.1:3110:8000", "--env-file", "/dev/stdin",
       "--mount", f"type=bind,source={root / 'tools/trial-local/serve.py'},target=/harness/trial.py,readonly",
       "--mount", f"type=bind,source={root / 'apps/api/app/guard/receipts.py'},target=/app/app/guard/receipts.py,readonly",
       source["Image"], "python", "/harness/trial.py",
       input="".join(f"{key}={value}\n" for key, value in env.items()), text=True,
       stdout=subprocess.DEVNULL)
docker("network", "connect", edge, name, stdout=subprocess.DEVNULL)
docker("start", name, stdout=subprocess.DEVNULL)
print("Local trial API: http://localhost:3110")
print("Local inbox: http://localhost:3110/__trial/inbox")
