"""Explicit local-only recovery of a trial token lost with an ephemeral key."""
import argparse
import os
import secrets
import uuid
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidTag
from sqlalchemy import text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace_id', type=uuid.UUID)
    parser.add_argument('--repair', action='store_true')
    args = parser.parse_args()
    database = urlsplit(os.environ.get('DATABASE_URL', ''))
    if database.hostname != 'postgres' or database.path != '/conduct_e2e':
        parser.error('This operation is restricted to the isolated local database')
    if not os.environ.get('CLERK_SECRET_KEY', '').startswith('sk_test_'):
        parser.error('A Clerk test instance is required')

    from app.core.crypto import decrypt, encrypt
    from app.core.database import engine
    from app.modules.agent_identity.adapters import TOKEN_PREFIX
    from app.modules.guard.trial_seed import TRIAL_IDENTITY_NAME

    with engine.begin() as db:
        row = db.execute(text('''
            SELECT id, token_encrypted FROM agent_identities
            WHERE workspace_id = :ws AND name = :name
              AND lifecycle_state = 'active' AND expires_at > now()
            ORDER BY created_at DESC LIMIT 1 FOR UPDATE
        '''), {'ws': str(args.workspace_id), 'name': TRIAL_IDENTITY_NAME}).mappings().first()
        if not row:
            parser.error('No active, unexpired local trial identity found')
        try:
            valid = bool(decrypt(row['token_encrypted']).get('token'))
        except InvalidTag:
            valid = False
        if valid:
            print('Existing local trial token decrypts successfully; no changes made')
            return
        if not args.repair:
            parser.error('Local trial token is unreadable; explicit --repair is required')
        token = TOKEN_PREFIX + secrets.token_hex(32)
        encrypted = encrypt({'token': token})
        assert decrypt(encrypted)['token'] == token
        db.execute(text('''
            UPDATE agent_identities SET token_prefix = :prefix, token_encrypted = :encrypted
            WHERE id = :id AND workspace_id = :ws
        '''), {'prefix': token[:len(TOKEN_PREFIX) + 4], 'encrypted': encrypted,
               'id': row['id'], 'ws': str(args.workspace_id)})
    print('Reissued one local trial token; identity, expiry, limits and history preserved')


if __name__ == '__main__':
    main()
