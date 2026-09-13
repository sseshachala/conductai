"""Migrate only the disposable database and prepare owner/restricted test roles."""
import os
import subprocess
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

url = os.environ['DATABASE_URL']
parsed = urlparse(url)
if parsed.hostname != 'postgres' or parsed.path != '/conduct_e2e' or parsed.username != 'postgres':
    raise SystemExit('Refusing to migrate anything except the isolated conduct_e2e database')
subprocess.run(['alembic', 'upgrade', 'head'], check=True)
subprocess.run(['python', 'scripts/seed_e2e_workspace.py'], check=True)
with create_engine(url).begin() as db:
    db.execute(text("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'conduct_e2e_app') THEN
            CREATE ROLE conduct_e2e_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'conduct_e2e_owner') THEN
            CREATE ROLE conduct_e2e_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
          END IF;
        END $$
    """))
    db.execute(text('GRANT USAGE, CREATE ON SCHEMA public TO conduct_e2e_owner'))
    # Match Render's table-owner behavior without granting superuser/BYPASSRLS.
    db.execute(text("""
        DO $$ DECLARE item record; BEGIN
          FOR item IN
            SELECT c.relname FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
              AND NOT EXISTS (
                SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass
                  AND d.objid = c.oid AND d.deptype = 'e'
              )
          LOOP
            EXECUTE format('ALTER TABLE public.%I OWNER TO conduct_e2e_owner', item.relname);
          END LOOP;
        END $$
    """))
    db.execute(text('GRANT USAGE ON SCHEMA public TO conduct_e2e_app'))
    db.execute(text('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO conduct_e2e_app'))
    db.execute(text('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO conduct_e2e_app'))
print('Migrations complete; restricted and table-owner roles available; neither has superuser/BYPASSRLS')
