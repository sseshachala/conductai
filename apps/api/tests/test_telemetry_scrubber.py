from app.core.telemetry import event_scrubber


def test_subject_evidence_and_existing_credentials_are_scrubbed():
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
