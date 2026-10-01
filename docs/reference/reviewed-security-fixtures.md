# Reviewed security fixtures

`no-private-key` stays enabled and non-overridable. A separate administrator can
approve one exact synthetic test-file edit for a workspace member. This is not
a path allowlist or a change to the rule's pattern.

## Review an edit

Use the updated API with migration `0161` and the matching CLI. Both Clerk and
OIDC deployments use the selected workspace's mapped user IDs and permissions.

Keep the proposed action JSON locally. It contains the complete tool name,
tool input and absolute working directory:

```json
{
  "tool_name": "write",
  "tool_input": {
    "file_path": "tests/fixture.txt",
    "content": "synthetic test material"
  },
  "cwd": "/absolute/path/to/repository"
}
```

`edit` and single-file `apply_patch` additions/updates are also supported.
Use the exact tool name and arguments emitted by the tool. Shell commands,
multi-file patches, deletes, moves and targets outside test directories are
not eligible. The file is read locally; its contents are never uploaded.

```sh
conduct guard fixture-review fingerprint --action-file proposed-action.json
```

A different workspace administrator must inspect the **entire edit**, confirm
that it contains no real credentials, and approve it using their own login:

```sh
conduct guard fixture-review approve --action-file proposed-action.json \
  --subject MAPPED_USER_ID --reviewed-synthetic \
  --reason "Reviewed synthetic security fixture" --ttl-seconds 600
conduct guard fixture-review list
conduct guard fixture-review revoke --approval APPROVAL_UUID
```

The administrator's acknowledgement is the review, not an automatic claim that
a marker is harmless. Do not approve a real credential. Approval records retain
the approver, subject, digest, expiry and reason, without storing edit contents.

## Enforcement

When `no-private-key` blocks that exact structured edit, the updated hook asks
the selected API to consume its approval. The approval is workspace- and
user-bound, single-use, and expires after at most one hour. The API commits the
consumption and audit entry before returning permission. Revoked, expired,
already-used and mismatched approvals cannot be consumed.

Only that rule is exempted for that exact action. The hook evaluates all other
rules again. Any changed content, tool name, target or working directory needs
a new review. Network errors and audit failures keep the original block, even
when the ordinary hook fail mode is fail-open. There is no offline approval cache.
Consumption does not promise that the editor successfully applied the edit.

Existing block receipts are retained. This does not exempt MCP response
inspection or alter the active hook installation. Upgrade and restart the
tool before testing the new flow.

## Acceptance still required

Issue #2317 remains open until the blocked private-key-shaped fixture is
approved through this deployed flow, runs successfully, and is restored to the
MCP inspection tests. This PR tests the approval mechanism with neutral synthetic
content; it does not disguise or bypass the currently blocked fixture.
