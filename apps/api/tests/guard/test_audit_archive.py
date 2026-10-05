import io
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.modules.guard.audit_archive import (
    ArchiveIntegrityError, S3ArchiveStore, archive_keys,
    manifest_object_key, persist_archive, read_verified_archive, verify_manifest,
)


@pytest.fixture
def archive_settings():
    return Settings(
        guard_audit_retention_enabled=True, guard_audit_retention_dry_run=False,
        guard_audit_retention_days=30, guard_audit_retention_batch_size=2,
        guard_audit_archive_bucket="test-archive",
        guard_audit_archive_signing_key=SecretStr("test-signing-key-not-for-production-1234"),
        guard_audit_archive_encryption_key=SecretStr("test-encryption-key-not-for-production-5678"),
    )


class MemoryStore:
    def __init__(self, on_write=None):
        self.objects = {}
        self.on_write = on_write

    def put_once(self, key, body):
        if self.on_write:
            self.on_write()
        self.objects.setdefault(key, body)
        return self.objects[key]

    def read(self, key):
        return self.objects[key]


def source_rows():
    return [{"id": "event-a", "workspace_id": "workspace-a", "ts": "2026-01-01T00:00:00+00:00",
             "entry_hash": None, "previous_hash": None, "input_summary": "private prompt content"}]


def test_encrypted_archive_retry_and_roundtrip(archive_settings):
    store = MemoryStore()
    rows = source_rows()
    manifest, signature = persist_archive(rows, "", 1, archive_settings, store)
    assert all(b"private prompt content" not in value for value in store.objects.values())
    assert read_verified_archive(manifest, signature, archive_settings, store, workspace_id="workspace-a") == rows
    retry, retry_signature = persist_archive(rows, "", 1, archive_settings, store)
    assert retry == manifest and retry_signature == signature
    assert len(store.objects) == 2


@pytest.mark.parametrize("target", ["payload", "manifest", "checkpoint", "signature", "workspace", "parent"])
def test_tampered_archive_is_rejected(archive_settings, target):
    store = MemoryStore()
    manifest, signature = persist_archive(source_rows(), "", 1, archive_settings, store)
    if target == "payload":
        store.objects[manifest["object_key"]] = b"corrupt"
    elif target == "manifest":
        store.objects[manifest_object_key(manifest)] = b"corrupt"
    elif target == "checkpoint":
        manifest = {**manifest, "event_count": 9}
    elif target == "signature":
        signature = "0" * 64
    signing, _ = archive_keys(archive_settings)
    with pytest.raises(ArchiveIntegrityError):
        if target == "parent":
            verify_manifest(manifest, signature, signing, workspace_id="workspace-a", previous_hash="wrong")
        else:
            read_verified_archive(manifest, signature, archive_settings, store,
                                  workspace_id="other-workspace" if target == "workspace" else "workspace-a")


def test_upload_readback_mismatch_is_rejected(archive_settings):
    class CorruptStore(MemoryStore):
        def put_once(self, key, body):
            return b"corrupt"
    with pytest.raises(ArchiveIntegrityError):
        persist_archive(source_rows(), "", 1, archive_settings, CorruptStore())


def test_storage_failure_stops_archive(archive_settings):
    store = MemoryStore(on_write=lambda: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(TimeoutError):
        persist_archive(source_rows(), "", 1, archive_settings, store)


def test_archive_requires_separate_keys_and_size_bound(archive_settings):
    archive_settings.guard_audit_archive_encryption_key = archive_settings.guard_audit_archive_signing_key
    with pytest.raises(ValueError, match="separate"):
        archive_keys(archive_settings)
    archive_settings.guard_audit_archive_encryption_key = SecretStr("test-separate-key-5678-abcdefghijklm")
    archive_settings.guard_audit_archive_max_bytes = 1024
    rows = source_rows()
    rows[0]["input_summary"] = "x" * 2000
    with pytest.raises(ArchiveIntegrityError, match="size"):
        persist_archive(rows, "", 1, archive_settings, MemoryStore())


def test_s3_conditional_write_and_bounded_readback(archive_settings):
    class Client:
        def put_object(self, **kwargs):
            self.put = kwargs
        def get_object(self, **kwargs):
            self.get = kwargs
            self.stream = io.BytesIO(b"stored")
            return {"Body": self.stream}
    client = Client()
    store = S3ArchiveStore(archive_settings, client=client)
    assert store.put_once("key", b"stored") == b"stored"
    assert client.put["IfNoneMatch"] == "*"
    assert client.get == {"Bucket": "test-archive", "Key": "key"}
    assert client.stream.closed
    store.max_bytes = 2
    with pytest.raises(ArchiveIntegrityError, match="size"):
        store.read("key")
    assert client.stream.closed


@pytest.mark.parametrize("endpoint", ["http://storage.test", "https://user:password@storage.test", "file:///archive"])
def test_untrusted_transport_settings_are_rejected(archive_settings, endpoint):
    archive_settings.guard_audit_archive_endpoint = endpoint
    with pytest.raises(ValueError, match="HTTPS"):
        S3ArchiveStore(archive_settings, client=object())


def test_retention_defaults_safe_off():
    configured = Settings(_env_file=None)
    assert configured.guard_audit_retention_enabled is False
    assert configured.guard_audit_retention_dry_run is True
    assert configured.guard_audit_retention_days is None


def test_s3_private_endpoint_credentials_and_ca(archive_settings, monkeypatch):
    import boto3
    calls = []
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: calls.append((args, kwargs)) or object())
    archive_settings.guard_audit_archive_endpoint = "https://minio.example.test"
    archive_settings.guard_audit_archive_ca_bundle = "/deployment/corporate-ca.pem"
    archive_settings.guard_audit_archive_path_style = True
    archive_settings.guard_audit_archive_access_key_id = SecretStr("test-access")
    archive_settings.guard_audit_archive_secret_access_key = SecretStr("test-secret")
    S3ArchiveStore(archive_settings)
    kwargs = calls[0][1]
    assert kwargs["endpoint_url"] == "https://minio.example.test"
    assert kwargs["verify"] == "/deployment/corporate-ca.pem"
    assert kwargs["config"].s3["addressing_style"] == "path"
    assert kwargs["config"].retries["total_max_attempts"] == 2
    assert kwargs["config"].read_timeout == kwargs["config"].connect_timeout == 10
    assert "test-secret" not in repr(archive_settings)
