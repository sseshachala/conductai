"""Locked, atomic edits of structured tool configuration; no shell evaluation."""
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile

from .credential_lock import credential_lock


@contextmanager
def edit_document(path):
    path = Path(path)
    with credential_lock(path):
        if path.is_symlink():
            raise ValueError("Symlinked configuration is not writable")
        if path.exists() and (not path.is_file() or path.stat().st_size > 1_000_000):
            raise ValueError("Invalid or oversized configuration")
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        if path.suffix == ".toml":
            import tomlkit
            document = tomlkit.parse(before)
            encode = tomlkit.dumps
        else:
            document = json.loads(before) if before else {}
            encode = lambda value: json.dumps(value, indent=2) + "\n"
        if not isinstance(document, dict):
            raise ValueError("Configuration must be an object")
        initial = encode(document)
        yield document
        after = encode(document)
        if after == initial:
            return
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(after)
        try:
            temporary.chmod(0o600)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
