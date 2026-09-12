import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('local', Path(__file__).with_name('local.py'))
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


def fake_clerk_key(prefix, environment):
    return f'{prefix}_{environment}_synthetic'


class PreflightTests(unittest.TestCase):
    def test_missing_configuration_is_not_success(self):
        self.assertEqual(len(local.preflight({})), 4)

    def test_live_keys_are_rejected(self):
        env = dict(CLERK_SECRET_KEY=fake_clerk_key('sk', 'live'), NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=fake_clerk_key('pk', 'live'),
                   CLERK_FRONTEND_API='clerk.example.com', E2E_ALLOW_TEST_USERS='1')
        self.assertEqual(len(local.preflight(env)), 3)

    def test_explicit_test_configuration(self):
        env = dict(CLERK_SECRET_KEY=fake_clerk_key('sk', 'test'), NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=fake_clerk_key('pk', 'test'),
                   CLERK_FRONTEND_API='synthetic.clerk.accounts.dev', E2E_ALLOW_TEST_USERS='1')
        self.assertEqual(local.preflight(env), [])


class DatabaseModeTests(unittest.TestCase):
    def check_mode(self, flags, expected_role, expected_mode):
        with patch.object(local.sys, 'argv', ['local.py', 'up', *flags]), \
             patch.object(local, 'preflight', return_value=[]), \
             patch.object(local, 'container_encryption_key', return_value='test-key-' * 4), \
             patch.object(local.subprocess, 'run') as run, \
             patch('builtins.print'):
            run.return_value.returncode = 0
            self.assertEqual(local.main(), 0)
            env = run.call_args.kwargs['env']
            self.assertEqual(env['E2E_DATABASE_ROLE'], expected_role)
            self.assertEqual(env['E2E_DATABASE_MODE'], expected_mode)

    def test_default_is_restricted_even_with_inherited_owner_environment(self):
        with patch.dict(local.os.environ, E2E_DATABASE_ROLE='conduct_e2e_owner', E2E_DATABASE_MODE='owner'):
            self.check_mode([], 'conduct_e2e_app', 'restricted')

    def test_owner_requires_explicit_flag(self):
        self.check_mode(['--database-mode', 'owner'], 'conduct_e2e_owner', 'owner')


class EncryptionKeyTests(unittest.TestCase):
    def inspected(self, key):
        return SimpleNamespace(returncode=0, stdout=json.dumps([{'Config': {
            'Labels': {'com.docker.compose.project': 'conduct-e2e'},
            'Env': ['ENCRYPTION_KEY=' + key] if key else [],
        }}]), stderr='')

    def test_reuses_existing_key_even_with_initialize_flag(self):
        with patch.object(local.subprocess, 'run', return_value=self.inspected('test-key-' * 4)):
            self.assertEqual(local.container_encryption_key({}, True), 'test-key-' * 4)

    def test_refuses_implicit_rotation(self):
        with patch.object(local.subprocess, 'run', return_value=self.inspected('test-key-' * 4)):
            with self.assertRaises(ValueError):
                local.container_encryption_key({'ENCRYPTION_KEY': 'different-' * 4})

    def test_requires_explicit_initialization(self):
        with patch.object(local.subprocess, 'run', return_value=self.inspected('')):
            with self.assertRaises(ValueError):
                local.container_encryption_key({})
            self.assertGreaterEqual(len(local.container_encryption_key({}, True)), 32)

    def test_ignores_inherited_development_placeholder(self):
        with patch.object(local.subprocess, 'run', return_value=self.inspected('test-key-' * 4)):
            self.assertEqual(local.container_encryption_key({'ENCRYPTION_KEY': 'dev-only-32-byte-key-change-this!'}), 'test-key-' * 4)

    def test_docker_access_failure_does_not_generate_a_key(self):
        with patch.object(local.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stderr='permission denied')):
            with self.assertRaises(ValueError):
                local.container_encryption_key({}, True)


if __name__ == '__main__':
    unittest.main()
