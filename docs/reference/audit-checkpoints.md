# Signed audit checkpoints: key setup

Signed chain-head checkpoints let an auditor detect deletion of the end of a workspace's Guard
audit chain. How to verify them is in [Audit log verification](../audit-log-verification.md#signed-chain-head-checkpoints-tail-truncation).
This page covers operator setup. The feature is off until a backend is chosen.

## Settings

| Setting | Meaning |
|---|---|
| `GUARD_AUDIT_CHECKPOINT_BACKEND` | `off` (default), `kms` or `local` |
| `GUARD_AUDIT_CHECKPOINT_KMS_KEY_ID` | KMS key id or ARN (`kms` only) |
| `GUARD_AUDIT_CHECKPOINT_KMS_REGION` | KMS region (`kms` only; default from the AWS environment) |
| `GUARD_AUDIT_CHECKPOINT_ED25519_PRIVATE_KEY` | `local` only: base64 of the raw 32-byte seed, or a PEM Ed25519 private key |
| `GUARD_AUDIT_CHECKPOINT_INTERVAL_SECONDS` | Worker cadence, default 3600 |
| `GUARD_AUDIT_CHECKPOINT_RETENTION_DAYS` | Default 365; the newest checkpoint per workspace is always kept |

The worker runs the job; the API only serves public keys and bundles checkpoints. The private key
is never logged or returned by any endpoint.

## AWS KMS (SaaS)

Create an asymmetric signing key. Ed25519 is preferred:

```bash
aws kms create-key --key-spec ECC_NIST_EDWARDS25519 --key-usage SIGN_VERIFY \
  --description "Conduct audit checkpoint signing"
```

If Ed25519 is not available in your region or partition, use `--key-spec ECC_NIST_P256`;
checkpoints then carry `alg: ECDSA-P256-SHA256`. Other key specs are rejected at startup.

Grant the worker role **only** `kms:Sign` and `kms:GetPublicKey` on this key:

```json
{
  "Sid": "ConductAuditCheckpointSigner",
  "Effect": "Allow",
  "Principal": {"AWS": "arn:aws:iam::ACCOUNT:role/conduct-worker"},
  "Action": ["kms:Sign", "kms:GetPublicKey"],
  "Resource": "*"
}
```

Do not grant `kms:ScheduleKeyDeletion`, `kms:DisableKey` or key-policy changes to the worker or
application roles; keep them with a separate security administrator and alert on `kms:Sign` calls
from any other principal in CloudTrail. The worker and API need no other KMS permission.

## Settings-held key (on-prem/dev)

```bash
python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"
```

Store the output in your secret manager and set `GUARD_AUDIT_CHECKPOINT_ED25519_PRIVATE_KEY`.
This gives offline verifiability but not protection from someone who can read the app's configuration.

## Rotation

Point the setting at a new key. The next checkpoint is signed with it (its `key_id` is a hash of
the public key). The old public key stays in `guard_audit_signing_keys` and at
`/.well-known/conduct-audit-keys`, so old checkpoints keep verifying. Do not delete old keys.

## Check it works

```bash
curl -s https://<api-host>/.well-known/conduct-audit-keys
```

returns your key after the first worker cycle. Log lines `guard.audit_checkpoint.completed` report
created, errors and deleted counts (error types only, no key or KMS detail).
