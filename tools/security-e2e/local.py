"""Operate the isolated local stack without loading repository credentials."""
import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ['rtk', 'docker', 'compose', '-f', str(ROOT / 'tools/security-e2e/compose.yml')]


def container_encryption_key(environment, initialize=False):
    """Reuse the container's configured key without printing or saving it."""
    inspected = subprocess.run(
        ['rtk', 'proxy', 'docker', 'inspect', 'conduct-e2e-api-1'],
        capture_output=True, text=True, env=environment,
    )
    existing = None
    if inspected.returncode == 0:
        container = json.loads(inspected.stdout)[0]
        if container['Config'].get('Labels', {}).get('com.docker.compose.project') != 'conduct-e2e':
            raise ValueError('Unexpected API container project; refusing key reuse')
        for entry in container['Config'].get('Env', []):
            name, _, value = entry.partition('=')
            if name == 'ENCRYPTION_KEY' and value:
                existing = value
    elif 'no such' not in (getattr(inspected, 'stdout', '') + inspected.stderr).lower():
        raise ValueError('Cannot inspect local API container; check Docker access')
    configured = environment.get('ENCRYPTION_KEY')
    # A development placeholder is not a usable key for this production-mode stack.
    placeholder = 'dev-only-32-byte-key-change-this!'
    if configured == placeholder:
        configured = None
    if existing == placeholder:
        existing = None
    if existing and configured and existing != configured:
        raise ValueError('ENCRYPTION_KEY differs from the running container; refusing implicit key rotation')
    key = configured or existing
    if not key and initialize:
        key = secrets.token_hex(32)
    if not key or len(key.encode()) < 32:
        raise ValueError('Provide ENCRYPTION_KEY or explicitly initialize with --initialize-local-key; old encrypted data requires its original key')
    return key


def preflight(environment):
    errors = []
    if not environment.get('CLERK_SECRET_KEY', '').startswith('sk_test_'):
        errors.append('CLERK_SECRET_KEY must belong to a separate Clerk test instance')
    if not environment.get('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY', '').startswith('pk_test_'):
        errors.append('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY must belong to that test instance')
    if not environment.get('CLERK_FRONTEND_API', '').endswith('.accounts.dev'):
        errors.append('CLERK_FRONTEND_API must be the test instance frontend domain')
    if environment.get('E2E_ALLOW_TEST_USERS') != '1':
        errors.append('E2E_ALLOW_TEST_USERS=1 is required to create/delete synthetic Clerk users')
    return errors


def web_preflight(environment):
    errors = preflight(environment)
    for role in ('admin', 'security', 'developer', 'viewer'):
        if not environment.get(role):
            errors.append(f"Missing Clerk sandbox password '{role}'")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'infra', 'up', 'test', 'web-test', 'stop', 'status'])
    parser.add_argument('--credentials-file', type=Path)
    parser.add_argument('--allow-test-users', action='store_true')
    parser.add_argument('--database-mode', choices=['restricted', 'owner'], default='restricted')
    parser.add_argument('--grep', help='Run only matching Playwright test titles')
    parser.add_argument('--initialize-local-key', action='store_true', help='Explicitly create a key if no configured/container key exists')
    args = parser.parse_args()
    action = args.action
    environment = os.environ.copy()
    environment['E2E_DATABASE_ROLE'] = 'conduct_e2e_owner' if args.database_mode == 'owner' else 'conduct_e2e_app'
    environment['E2E_DATABASE_MODE'] = args.database_mode
    if action in ('up', 'test'):
        print(f'Database mode: {args.database_mode}; owner mode does not validate RLS enforcement', flush=True)
    if args.credentials_file:
        from dotenv import dotenv_values
        if not args.credentials_file.is_file():
            parser.error('Credential file does not exist')
        values = dotenv_values(args.credentials_file, interpolate=False)
        for key in (
            'CLERK_SECRET_KEY', 'NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY',
            'CLERK_FRONTEND_API', 'CLERK_AUDIENCE', 'ENCRYPTION_KEY',
            'admin', 'security', 'developer', 'viewer',
        ):
            if values.get(key):
                environment[key] = values[key].strip()
    frontend = environment.get('CLERK_FRONTEND_API', '')
    if '://' in frontend:
        parsed = urlsplit(frontend)
        if parsed.scheme != 'https' or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username or parsed.port:
            parser.error('Clerk frontend must be a hostname or a plain HTTPS origin')
        environment['CLERK_FRONTEND_API'] = parsed.hostname or ''
    if args.allow_test_users:
        environment['E2E_ALLOW_TEST_USERS'] = '1'
    if action in ('check', 'up', 'test', 'web-test'):
        errors = web_preflight(environment) if action == 'web-test' else preflight(environment)
        if errors:
            print('Authenticated E2E prerequisites missing:', file=sys.stderr)
            for error in errors:
                print('  - ' + error, file=sys.stderr)
            return 2
    if action == 'check':
        print('Clerk test configuration present (values not displayed); remote validity is not yet verified')
        return 0
    if action == 'up':
        try:
            environment['ENCRYPTION_KEY'] = container_encryption_key(environment, args.initialize_local_key)
        except ValueError as error:
            parser.error(str(error))
    commands = {
        'infra': COMPOSE + ['up', '-d', '--wait', 'postgres', 'redis'],
        'up': COMPOSE + ['--profile', 'application', 'up', '-d', '--build', '--wait'],
        'stop': COMPOSE + ['--profile', 'application', 'stop'],
        'status': COMPOSE + ['--profile', 'application', 'ps'],
        'test': ['rtk', 'proxy', 'npx', 'playwright', 'test', '--config', 'playwright.security.config.ts'],
        'web-test': ['rtk', 'proxy', 'npx', 'playwright', 'test', '--config', 'playwright.config.ts'],
    }
    browser_test = action in ('test', 'web-test')
    cwd = ROOT / 'apps/web' if browser_test else ROOT
    if action == 'web-test':
        environment['PLAYWRIGHT_BASE_URL'] = 'http://localhost:3100'
        environment['NEXT_PUBLIC_API_URL'] = '/api'
    if args.grep and browser_test:
        commands[action] += ['--grep', args.grep]
    if browser_test:
        with subprocess.Popen(commands[action], cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
            for line in process.stdout:
                line = re.sub(r'(__clerk_db_jwt|__clerk_testing_token)=[^&\s)]+', r'\1=[redacted]', line)
                line = re.sub(r'Bearer\s+[A-Za-z0-9._-]+', 'Bearer [redacted]', line)
                for key in ('CLERK_SECRET_KEY',):
                    if environment.get(key):
                        line = line.replace(environment[key], '[redacted]')
                print(line, end='', flush=True)
            return process.wait()
    return subprocess.run(commands[action], cwd=cwd, env=environment).returncode


if __name__ == '__main__':
    raise SystemExit(main())
