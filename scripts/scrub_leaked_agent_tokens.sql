-- Revoke agent tokens whose value leaked into git history.
--
-- Auth path (apps/api/app/core/auth.py lines 222, 363, 861) rejects
-- lifecycle_state = 'deactivated' at three call sites, so setting this
-- state on a matching row makes any prior copy of the token unusable.
--
-- Prefixes below are the first 13 chars (cond_agt_ + 4 hex chars) of
-- tokens found in git history across sseshachala/conductai on 2026-08-26.
--
-- Run in a transaction so you can inspect + rollback if needed.

BEGIN;

-- Preview: which rows will be affected.
SELECT id, workspace_id, name, token_prefix, lifecycle_state, created_at, last_used_at
FROM   agent_identities
WHERE  token_prefix IN (
  'cond_agt_1964',
  'cond_agt_6a58',
  'cond_agt_8158'
);

-- Revoke.
UPDATE agent_identities
SET    lifecycle_state = 'deactivated',
       deactivated_at  = NOW(),
       metadata_json   = COALESCE(metadata_json, '{}'::jsonb) ||
                         jsonb_build_object(
                           'revoked_reason', 'leaked-public-repo-2026-08-24',
                           'revoked_at',     to_char(NOW() AT TIME ZONE 'UTC',
                                                    'YYYY-MM-DD"T"HH24:MI:SS"Z"')
                         )
WHERE  token_prefix IN (
  'cond_agt_1964',
  'cond_agt_6a58',
  'cond_agt_8158'
)
AND    lifecycle_state <> 'deactivated';

-- Verify.
SELECT id, token_prefix, lifecycle_state, deactivated_at, metadata_json
FROM   agent_identities
WHERE  token_prefix IN (
  'cond_agt_1964',
  'cond_agt_6a58',
  'cond_agt_8158'
);

-- If everything looks right:
--   COMMIT;
-- Otherwise:
--   ROLLBACK;
