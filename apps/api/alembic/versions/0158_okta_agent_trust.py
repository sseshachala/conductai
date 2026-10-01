"""Separate Okta agent trust from service credentials, with rolling compatibility."""
from alembic import op
import sqlalchemy as sa

revision = "0158"
down_revision = "0157"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.execute("SET LOCAL statement_timeout = '60s'")
    op.add_column("federation_connections", sa.Column(
        "authentication_mode", sa.String(32), nullable=False, server_default="delegated"))
    op.drop_constraint("federation_connections_integration_id_key", "federation_connections", type_="unique")
    op.create_unique_constraint("uq_federation_integration_mode", "federation_connections",
                                ["integration_id", "authentication_mode"])
    op.create_check_constraint("ck_federation_authentication_mode", "federation_connections",
                               "authentication_mode IN ('delegated', 'okta_agent')")
    # Old application versions may still write the three compatibility columns.
    # Keep that bridge transactional until those columns are removed separately.
    op.execute(r"""
    CREATE FUNCTION sync_okta_agent_trust() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE previous_workspace text; trust jsonb; state text;
    BEGIN
      IF TG_OP = 'DELETE' THEN
        previous_workspace := current_setting('app.current_workspace', true);
        PERFORM set_config('app.current_workspace', OLD.workspace_id::text, true);
        DELETE FROM federation_connections WHERE integration_id = OLD.id
          AND workspace_id = OLD.workspace_id AND authentication_mode = 'okta_agent';
        PERFORM set_config('app.current_workspace', coalesce(previous_workspace, ''), true);
        RETURN OLD;
      END IF;
      IF NEW.handle <> 'okta' THEN RETURN NEW; END IF;
      state := CASE WHEN NOT NEW.okta_auth_enabled THEN 'disabled'
        WHEN NEW.okta_issuer ~ '^https://[^/?#@[:space:]]+(/[^?#[:space:]]*)?$'
          AND length(btrim(NEW.okta_audience)) > 0 THEN 'active'
        ELSE 'needs_review' END;
      trust := jsonb_build_object('issuer', NEW.okta_issuer, 'audience', NEW.okta_audience,
        'jwks_uri', CASE WHEN NEW.okta_issuer IS NOT NULL
          THEN rtrim(NEW.okta_issuer, '/') || '/v1/keys' ELSE NULL END,
        'status', state, 'requested_enabled', NEW.okta_auth_enabled,
        'token_profile', 'okta_agent_jwt', 'algorithms', jsonb_build_array('RS256'));
      previous_workspace := current_setting('app.current_workspace', true);
      PERFORM set_config('app.current_workspace', NEW.workspace_id::text, true);
      INSERT INTO federation_connections
        (id, workspace_id, integration_id, authentication_mode, revision, config, created_at, updated_at)
        VALUES (gen_random_uuid(), NEW.workspace_id, NEW.id, 'okta_agent', 1, trust, now(), now())
      ON CONFLICT (integration_id, authentication_mode) DO UPDATE
        SET config = EXCLUDED.config, revision = federation_connections.revision + 1, updated_at = now()
        WHERE federation_connections.config IS DISTINCT FROM EXCLUDED.config;
      PERFORM set_config('app.current_workspace', coalesce(previous_workspace, ''), true);
      RETURN NEW;
    END $$;
    CREATE TRIGGER integrations_okta_trust_sync AFTER INSERT OR UPDATE OF
      okta_issuer, okta_audience, okta_auth_enabled ON integrations
      FOR EACH ROW EXECUTE FUNCTION sync_okta_agent_trust();
    CREATE TRIGGER integrations_okta_trust_delete BEFORE DELETE ON integrations
      FOR EACH ROW EXECUTE FUNCTION sync_okta_agent_trust();
    """)
    # Repeating this statement is safe: unchanged configuration keeps its revision.
    op.execute("UPDATE integrations SET okta_auth_enabled = okta_auth_enabled WHERE handle = 'okta'")


def downgrade():
    # Compatibility columns retain the settings for an application rollback.
    # Schema rollback must not silently delete trust records.
    op.execute("LOCK TABLE federation_connections IN ACCESS EXCLUSIVE MODE")
    for workspace in op.get_bind().execute(sa.text("SELECT id FROM workspaces")).scalars().all():
        op.get_bind().execute(sa.text("SELECT set_config('app.current_workspace', :ws, true)"), {"ws": str(workspace)})
        if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM federation_connections "
                                        "WHERE authentication_mode = 'okta_agent')")).scalar_one():
            raise RuntimeError("Okta trust requires a data-preserving rollback plan")
    op.execute("DROP TRIGGER integrations_okta_trust_sync ON integrations")
    op.execute("DROP TRIGGER integrations_okta_trust_delete ON integrations")
    op.execute("DROP FUNCTION sync_okta_agent_trust()")
    op.drop_constraint("ck_federation_authentication_mode", "federation_connections", type_="check")
    op.drop_constraint("uq_federation_integration_mode", "federation_connections", type_="unique")
    op.create_unique_constraint("federation_connections_integration_id_key", "federation_connections", ["integration_id"])
    op.drop_column("federation_connections", "authentication_mode")
