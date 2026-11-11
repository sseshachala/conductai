"""`conduct audit verify` signed chain-head checkpoints (#2524 item 2).

Fixtures are signed by the API's real signer (apps/api/app/modules/guard/audit_signing.py)
with a public test seed; apps/api/tests/guard/test_audit_checkpoints.py::test_cli_fixture_checkpoint_verifies_with_api
pins the API verifier to the same bytes.
"""
import argparse
import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from conduct_cli.commands.audit import cmd_audit, verify_lines

FIX = Path(__file__).parent / "fixtures"
CHAIN = (FIX / "audit_export_chain.ndjson").read_text().splitlines()
BUNDLE = json.loads((FIX / "audit_checkpoint_bundle.json").read_text())      # pins row 5 (the head)
BUNDLE3 = json.loads((FIX / "audit_checkpoint_bundle_row3.json").read_text())  # pins row 3


def _trailer(bundle):
    return json.dumps({"kind": "audit_checkpoint", "checkpoint": bundle["checkpoint"], "keys": bundle["keys"]})


def _export(lines=None, bundle=BUNDLE):
    return list(lines if lines is not None else CHAIN) + [_trailer(bundle)]


def test_export_with_valid_checkpoint_passes():
    res = verify_lines(_export())
    assert res["ok"] and res["rows"] == 5 and res["checkpoint"]["status"] == "valid"
    assert res["checkpoint"]["trusted_keys"] is False  # bundled keys are not independent


def test_tail_truncated_export_fails():
    res = verify_lines(_export(CHAIN[:3]))
    assert not res["ok"] and res["checkpoint"]["status"] == "truncated"
    assert "ends before the checkpoint head" in res["broken"]["reason"]


def test_truncation_fails_even_when_chain_is_still_valid():
    assert verify_lines(CHAIN[:3])["ok"]  # without the checkpoint the cut is invisible


@pytest.mark.parametrize("field,value", [("row_count", 4), ("head_entry_hash", "0" * 64),
                                         ("ts", "2026-11-12T00:00:00.000000Z"), ("key_id", "x")])
def test_tampered_checkpoint_fails(field, value):
    bundle = {"checkpoint": {**BUNDLE["checkpoint"], field: value}, "keys": BUNDLE["keys"]}
    res = verify_lines(_export(bundle=bundle))
    assert not res["ok"] and res["checkpoint"]["status"] in ("invalid", "unknown_key")


def test_tampered_signature_fails():
    sig = bytearray(base64.b64decode(BUNDLE["checkpoint"]["signature"]))
    sig[0] ^= 1
    bundle = {"checkpoint": {**BUNDLE["checkpoint"], "signature": base64.b64encode(bytes(sig)).decode()},
              "keys": BUNDLE["keys"]}
    assert not verify_lines(_export(bundle=bundle))["ok"]


def test_independent_keys_are_trusted_and_wrong_key_fails():
    res = verify_lines(_export(), keys=BUNDLE["keys"])
    assert res["ok"] and res["checkpoint"]["trusted_keys"] is True
    # A forger who swaps in their own key inside the export is caught by pinned keys.
    other = json.loads(json.dumps(BUNDLE["keys"]))
    key_id = next(iter(other))
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    forger = ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    other[key_id]["public_key"] = base64.b64encode(forger).decode()
    assert not verify_lines(_export(), keys=other)["ok"]
    assert not verify_lines(_export(), keys={})["ok"]  # unknown key


def test_older_checkpoint_in_middle_of_export_is_ok():
    res = verify_lines(_export(bundle=BUNDLE3))
    assert res["ok"] and res["checkpoint"]["status"] == "valid"


def test_checkpoint_before_a_later_slice_is_not_covered():
    res = verify_lines(_export(CHAIN[3:], bundle=BUNDLE3))
    assert res["ok"] and res["checkpoint"]["status"] == "not_covered"


def test_row_replaced_at_head_position_fails():
    bad = json.loads(CHAIN[4])
    bad["entry_hash"] = "f" * 64  # would fail the chain anyway; use allow_gaps to isolate checkpoint logic
    lines = CHAIN[:4] + [json.dumps(bad)]
    res = verify_lines(_export(lines), allow_gaps=True)
    assert not res["ok"]


def test_no_checkpoint_passes_unless_required():
    assert verify_lines(CHAIN)["checkpoint"]["status"] == "none"
    res = verify_lines(CHAIN, require_checkpoint=True)
    assert not res["ok"] and "no signed checkpoint" in res["broken"]["reason"]


def test_checkpoint_option_overrides_trailer():
    res = verify_lines(CHAIN[:3], checkpoint=BUNDLE["checkpoint"], bundled_keys=BUNDLE["keys"])
    assert not res["ok"] and res["checkpoint"]["status"] == "truncated"


def test_cli_end_to_end(tmp_path, capsys):
    good = tmp_path / "good.ndjson"
    good.write_text("\n".join(_export()) + "\n")
    keys = tmp_path / "keys.json"
    keys.write_text(json.dumps({"keys": BUNDLE["keys"]}))
    args = argparse.Namespace(audit_command="verify", file=str(good), allow_gaps=False, keys=str(keys),
                              checkpoint=None, require_checkpoint=False)
    cmd_audit(args)
    out = capsys.readouterr().out
    assert out.startswith("OK: 5 rows") and "Checkpoint OK" in out and "Warning" not in out

    cut = tmp_path / "cut.ndjson"
    cut.write_text("\n".join(_export(CHAIN[:3])) + "\n")
    args.file = str(cut)
    with pytest.raises(SystemExit) as exc:
        cmd_audit(args)
    assert exc.value.code == 1
    assert "ends before the checkpoint head" in capsys.readouterr().err
