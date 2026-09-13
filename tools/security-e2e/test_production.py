import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

directory = Path(__file__).parent
sys.path.insert(0, str(directory))
spec = importlib.util.spec_from_file_location('production', directory / 'production.py')
production = importlib.util.module_from_spec(spec)
spec.loader.exec_module(production)


class PlaywrightCommandTests(unittest.TestCase):
    def test_uses_rtk_when_available(self):
        with patch.object(production.shutil, 'which', return_value='/usr/local/bin/rtk'):
            self.assertEqual(production.playwright_command()[:3], ['rtk', 'proxy', 'npx'])

    def test_runs_directly_on_github_runner(self):
        with patch.object(production.shutil, 'which', return_value=None):
            self.assertEqual(production.playwright_command()[:2], ['npx', 'playwright'])


if __name__ == '__main__':
    unittest.main()
