"""Secret filtering shared by error and transaction telemetry."""
from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber


def event_scrubber():
    return EventScrubber(
        denylist=[*DEFAULT_DENYLIST, "conduct-subject-token"], recursive=True,
    )
