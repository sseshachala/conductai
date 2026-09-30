import importlib.util
from pathlib import Path
import time
import base64
import json

import pytest

spec = importlib.util.spec_from_file_location("live", Path(__file__).with_name("live.py"))
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


def test_revocation_requires_grant_diagnostic_not_generic_denial():
    assert live.expected_grant_denial(True, 403, True, "federation_grant_invalid")
    assert not live.expected_grant_denial(False, 403, True, "federation_grant_invalid")
    assert not live.expected_grant_denial(True, 401, True, "caller_token_not_recognized")
    assert not live.expected_grant_denial(True, 403, True, "federation_evidence_expired")


def test_expired_subject_cannot_pass_as_revoked():
    encode = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
    token = encode({"alg": "RS256"}) + "." + encode({
        "iss": "https://idp.test", "sub": "alice", "aud": "conduct", "token_use": "access", "exp": time.time() - 10,
    }) + ".synthetic"
    with pytest.raises(live.TestError, match="expired"):
        live.check_claims(token, {"issuer": "https://idp.test", "audience": "conduct"}, {"subject": "alice"})
