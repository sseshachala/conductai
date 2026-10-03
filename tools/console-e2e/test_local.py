"""Launcher checks without Docker, credentials, or live IdP requests."""
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import local
import yaml


class BuildInputsTests(unittest.TestCase):
    def test_gateway_v2_is_enabled_only_for_fixture_workspace(self):
        compose = yaml.safe_load(Path(__file__).with_name("compose.yml").read_text())
        environment = compose["services"]["api"]["environment"]
        self.assertEqual(environment["GUARD_GATEWAY_PROFILE_V2"], "true")
        self.assertEqual(environment["GUARD_GATEWAY_PROFILE_V2_ROLLOUT_PCT"], "0")
        self.assertEqual(environment["GUARD_GATEWAY_PROFILE_V2_ALLOWLIST"],
                         "bbbbbbbb-0000-4000-8000-000000000001")

    def test_shared_config_is_in_web_image(self):
        root = Path(__file__).resolve().parents[2]
        dockerfile = (root / "tools/security-e2e/web.Dockerfile").read_text()
        self.assertIn("COPY config ./config", dockerfile.split("RUN npm run build")[0])
        for name in ("ai_tools.json", "transports.json"):
            self.assertTrue((root / "config" / name).is_file())


class DiscoveryTests(unittest.TestCase):
    issuer = "https://keycloak.test/realms/console"

    def response(self, **overrides):
        doc = {"issuer": self.issuer, "jwks_uri": self.issuer + "/protocol/openid-connect/certs"}
        doc.update(overrides)
        return io.BytesIO(json.dumps(doc).encode())

    def test_valid_discovery(self):
        with patch.object(local.urllib.request, "urlopen", return_value=self.response()):
            self.assertEqual(local.metadata(self.issuer)["issuer"], self.issuer)

    def test_mismatched_issuer(self):
        with patch.object(local.urllib.request, "urlopen", return_value=self.response(issuer="https://other.test")):
            with self.assertRaises(ValueError):
                local.metadata(self.issuer)

    def test_cross_origin_jwks(self):
        with patch.object(local.urllib.request, "urlopen", return_value=self.response(jwks_uri="https://other.test/keys")):
            with self.assertRaises(ValueError):
                local.metadata(self.issuer)

    def test_reject_insecure_or_credential_urls(self):
        for issuer in ("http://keycloak.test", "https://user:secret@keycloak.test", "https://keycloak.test?x=y"):
            with self.subTest(issuer=issuer), self.assertRaises(ValueError):
                local.metadata(issuer)

    def test_oversized_document(self):
        with patch.object(local.urllib.request, "urlopen", return_value=io.BytesIO(b" " * 65537)):
            with self.assertRaises(ValueError):
                local.metadata(self.issuer)


if __name__ == "__main__":
    unittest.main()
