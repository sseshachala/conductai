"""Toggle only the known disposable fixture's viewer mapping; no remote DB access."""
import argparse
import subprocess

CODE = '''
import os, sys
from sqlalchemy import select
from app.core.database import SessionLocal
from app.modules.auth.console.models import ConsoleIdentityMapping
from app.models.workspace import Workspace
from uuid import UUID
assert os.environ.get("DATABASE_URL") == "postgresql://postgres@postgres/conduct_console_e2e"
with SessionLocal.begin() as db:
    ws = db.get(Workspace, UUID("bbbbbbbb-0000-4000-8000-000000000001"))
    assert ws is not None
    mapping = db.scalar(select(ConsoleIdentityMapping).where(
        ConsoleIdentityMapping.issuer == os.environ["CONSOLE_OIDC_ISSUER"],
        ConsoleIdentityMapping.subject == os.environ["TEST_VIEWER_SUBJECT"]))
    assert mapping is not None and mapping.user_id != ws.owner_id
    mapping.active = sys.argv[1] == "enable"
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enable", "disable"))
    args = parser.parse_args()
    result = subprocess.run(["rtk", "proxy", "docker", "exec", "-i", "conduct-console-e2e-api-1",
                             "python", "-", args.action], input=CODE, text=True, capture_output=True)
    if result.returncode:
        raise SystemExit("Local fixture mapping update failed; response suppressed")


if __name__ == "__main__":
    main()
