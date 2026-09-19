"""Build .ics calendar invites for jobs (ics lib)."""

from ics import Calendar, Event, Organizer


def build_job_ics(
    summary: str,
    description: str,
    location: str,
    start_iso: str,
    end_iso: str,
    organizer_email: str,
) -> bytes:
    """Build a Calendar with one Event and return its UTF-8 bytes."""
    event = Event(
        name=summary,
        description=description,
        location=location,
        begin=start_iso,
        end=end_iso,
        organizer=Organizer(email=organizer_email),
    )
    calendar = Calendar(events=[event])
    return str(calendar).encode("utf-8")
