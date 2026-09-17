#!/usr/bin/env python3
"""Provision an isolated local Docker fixture and exercise 1-2 MCP agents."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
COMPOSE = ['docker', 'compose', '-f', str(HERE / 'local.compose.yml')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agents', type=int, choices=[1, 2], default=2)
    parser.add_argument('--endpoint', choices=['/guard/mcp', '/mcp'], default='/mcp')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--unconfigured', action='store_true', help='Verify missing Guard setup blocks every check')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output directory must not exist')
    env = dict(os.environ, MCP_CANARY_ENCRYPTION_KEY=secrets.token_hex(32))
    fixture = None

    def compose(*command, **kwargs):
        return subprocess.run(COMPOSE + list(command), env=env, check=True, **kwargs)

    def fixture_call(payload):
        # Credentials cross a private subprocess pipe, never files or terminal output.
        code = (HERE / 'local_fixture.py').read_text()
        result = compose('exec', '-T', 'api', 'python', '-c', code,
                         input=json.dumps(payload), text=True, capture_output=True)
        try:
            return json.loads(result.stdout.splitlines()[-1])
        except Exception:
            raise RuntimeError('Invalid fixture response; raw output suppressed') from None

    try:
        compose('up', '-d', '--wait', 'postgres', 'redis')
        compose('run', '--rm', '--no-deps', 'api', 'alembic', 'upgrade', 'head')
        compose('up', '-d', 'api')
        for _ in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:3120/ready', timeout=2) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError('Local API did not become ready')
        fixture = fixture_call({'action': 'seed', 'agents': args.agents, 'install_guard': not args.unconfigured})
        config = json.loads((HERE / 'example.json').read_text())
        config.update(base_url='http://127.0.0.1:3120', endpoint=args.endpoint,
                      workspace_id=fixture['workspace_id'], duration_seconds=15,
                      rps=2, max_requests=40, reconnect_every=0, drain_seconds=10)
        config['agents'] = []
        # The default MCP audit-all rule permits execution but stores "audited".
        config['scenarios'][0]['audit_decision'] = 'audited'
        if args.unconfigured:
            config['scenarios'][0].update(name='missing_guard', decision='blocked', audit_decision='blocked')
        for i, agent in enumerate(fixture['agents']):
            key = f'CANARY_LOCAL_AGENT_{i}'
            env[key] = agent['token']
            config['agents'].append({'id': agent['id'], 'token_env': key})
        env[config['observer_token_env']] = fixture['observer']['token']
        print('Local workspace: ' + fixture['workspace_id'], flush=True)
        # Fresh interpreter: Locust monkey-patching cannot affect provisioning/cleanup.
        result = subprocess.run([
            sys.executable, '-c',
            'import json,sys; from pathlib import Path; from core import validate; '
            'from run import run; sys.exit(run(validate(json.load(sys.stdin)), Path(sys.argv[1])))',
            str(args.output.resolve()),
        ], cwd=HERE, env=env, input=json.dumps(config), text=True)
        return result.returncode
    finally:
        try:
            if fixture:
                fixture_call({'action': 'revoke', 'workspace_id': fixture['workspace_id']})
                print('Canary credentials revoked; workspace and audit evidence retained.', flush=True)
        finally:
            compose('stop', 'api')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError:
        # A fixture error can contain token-bearing SQL parameters; never print it.
        raise SystemExit('Local Docker step failed; sensitive subprocess output suppressed.') from None
