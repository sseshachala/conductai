import subprocess
import sys


def test_subject_evidence_and_existing_credentials_are_scrubbed():
    # Legacy collection-time SDK stubs must not replace the real scrubber under test.
    result = subprocess.run([sys.executable, "-c", '''
from app.core.telemetry import event_scrubber

def verify():
    event = {"request": {"headers": {
        "Conduct-Subject-Token": "synthetic-subject-evidence",
        "Authorization": "Bearer synthetic-caller",
        "Conduct-Federation-Connection": "connection-reference",
    }}}
    event_scrubber().scrub_event(event)
    headers = event["request"]["headers"]
    assert headers["Conduct-Subject-Token"].value == "[Filtered]"
    assert headers["Authorization"].value == "[Filtered]"
    assert headers["Conduct-Federation-Connection"] == "connection-reference"

verify()
'''], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
