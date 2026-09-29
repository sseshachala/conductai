"""Reproduce migration 0154 contention on a disposable local PostgreSQL DB."""
import os
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError


def main():
    url = make_url(os.environ["DATABASE_URL"])
    if url.host not in ("127.0.0.1", "localhost") or url.database != "conduct_migration_test":
        raise SystemExit("Requires disposable loopback database conduct_migration_test")
    api = Path(__file__).resolve().parents[2] / "apps" / "api"
    command = ["rtk", "proxy", sys.executable, "-m", "alembic"]

    def migrate(*args):
        return subprocess.run(command + list(args), cwd=api, capture_output=True, text=True, timeout=30)

    baseline = migrate("upgrade", "0153")
    assert baseline.returncode == 0, baseline.stderr
    engine = create_engine(url)
    with engine.connect() as reader:
        reader.execute(text("SELECT id FROM integrations LIMIT 1"))
        with engine.connect() as contender:
            contender.execute(text("SET LOCAL lock_timeout='200ms'"))
            try:
                contender.execute(text("ALTER TABLE integrations ADD CONSTRAINT regression_probe UNIQUE (workspace_id, id)"))
            except OperationalError as error:
                assert "lock timeout" in str(error)
                contender.rollback()
            else:
                raise AssertionError("Original migration unexpectedly obtained its exclusive lock")
        # API and Gateway start against the same schema, while the reader's
        # transaction remains open. Both upgrades must succeed without a race.
        processes = [subprocess.Popen(command + ["upgrade", "0154"], cwd=api,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for _ in range(2)]
        try:
            for process in processes:
                _, stderr = process.communicate(timeout=20)
                assert process.returncode == 0, stderr
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        reader.rollback()
    with engine.connect() as db:
        assert db.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0154"
        assert db.execute(text("SELECT count(*) FROM pg_constraint WHERE conname='fk_federation_integration_workspace'")).scalar_one() == 1

    empty_rollback = migrate("downgrade", "0153")
    assert empty_rollback.returncode == 0, empty_rollback.stderr
    with engine.connect() as writer:
        writer.execute(text("UPDATE integrations SET handle=handle WHERE false"))
        start = time.monotonic()
        blocked = migrate("upgrade", "0154")
        assert blocked.returncode != 0 and "lock timeout" in blocked.stderr, blocked.stderr
        assert time.monotonic() - start < 10
        writer.rollback()
    recovered = migrate("upgrade", "0154")
    assert recovered.returncode == 0, recovered.stderr
    engine.dispose()
    print("PASS: original lock regression reproduced; two serialized upgrades succeed with live reader; writer contention fails promptly; retry succeeds")


if __name__ == "__main__":
    main()
