import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

directory = Path(__file__).parent
sys.path.insert(0, str(directory))
spec = importlib.util.spec_from_file_location('production', directory / 'production.py')
production = importlib.util.module_from_spec(spec)
spec.loader.exec_module(production)


class PlaywrightCommandTests(unittest.TestCase):
    def test_restore_requires_explicit_mutation_consent(self):
        with patch.object(sys, 'argv', ['production', '--credentials-file', 'fixture.env', '--restore-gateway-fixtures']), \
             self.assertRaises(SystemExit):
            production.main()

    def test_restore_cannot_be_combined_with_read_only_preflight(self):
        with patch.object(sys, 'argv', ['production', '--gateway-preflight', '--restore-gateway-fixtures']), \
             self.assertRaises(SystemExit):
            production.main()

    def test_transport_only_reuses_shared_checks_without_browser_credentials(self):
        with patch.object(sys, 'argv', ['production', '--transport-only', '--transport-config', 'test.json']), \
             patch.object(production.transport_checks, 'validate_arguments') as validate, \
             patch.object(production.transport_checks, 'run', return_value=0) as run, \
             patch.object(production.subprocess, 'Popen') as popen:
            self.assertEqual(production.main(), 0)
            self.assertEqual(validate.call_args.args[1], 'saas')
            self.assertEqual(run.call_args.args[1], 'saas')
            popen.assert_not_called()

    def test_read_only_gateway_preflight_cannot_run_inference_stage(self):
        with patch.object(sys, 'argv', ['production', '--gateway-preflight', '--transport-config', 'test.json']), \
             self.assertRaises(SystemExit):
            production.main()

    def test_uses_rtk_when_available(self):
        with patch.object(production.shutil, 'which', return_value='/usr/local/bin/rtk'):
            self.assertEqual(production.playwright_command()[:3], ['rtk', 'proxy', 'npx'])

    def test_runs_directly_on_github_runner(self):
        with patch.object(production.shutil, 'which', return_value=None):
            self.assertEqual(production.playwright_command()[:2], ['npx', 'playwright'])

    def test_gateway_preflight_runs_only_fixture_check_without_mutation_consent(self):
        accounts = {
            'PROD_E2E_A_EMAIL': 'a@example.invalid',
            'PROD_E2E_B_EMAIL': 'b@example.invalid',
            'PROD_E2E_A_PASSWORD': 'synthetic-a',
            'PROD_E2E_B_PASSWORD': 'synthetic-b',
        }
        process = MagicMock()
        process.stdout = []
        process.wait.return_value = 0
        with patch.object(sys, 'argv', ['production', '--credentials-file', 'fixture.env',
                                       '--manual-otp', '--gateway-preflight', '--grep', 'ignored']), \
             patch.object(Path, 'is_file', return_value=True), \
             patch.object(production, 'dotenv_values', return_value=accounts), \
             patch.object(production.subprocess, 'Popen') as popen:
            popen.return_value.__enter__.return_value = process
            self.assertEqual(production.main(), 0)
            args, kwargs = popen.call_args
            self.assertEqual(args[0][-2:], ['--grep', '@prod-gateway-fixture'])
            self.assertEqual(kwargs['env']['PROD_E2E_GATEWAY_PREFLIGHT'], '1')


if __name__ == '__main__':
    unittest.main()
