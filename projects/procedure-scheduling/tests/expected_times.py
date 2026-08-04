"""Expected seeded start times, computed independently of scripts/seed.py.

The seed places every procedure at a LOCAL wall-clock time on the first
weekday at or after `today + day_offset` (Doug's 2026-08-04 decision). Tests
need the resulting UTC instant, but must not import the seed's own helper —
otherwise a bug in that helper would be invisible. This is a deliberate
second implementation, written from the documented rule, with the expected
clock values hardcoded at each call site.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# The local timezone a reader of the calendar sees; the seed converts local
# wall-clock times to UTC using this.
LOCAL_TZ = datetime.now().astimezone().tzinfo


def local_midnight_utc(reference: datetime) -> datetime:
    """Midnight UTC on the reference date — the seed's date anchor."""
    return reference.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def expected_start(
    anchor: datetime, day_offset: int, hour: int, minute: int = 0
) -> datetime:
    """The UTC instant for a seeded row: `hour:minute` LOCAL time on the first
    weekday at or after ``anchor + day_offset``."""
    day = anchor + timedelta(days=day_offset)
    while day.weekday() >= 5:  # Saturday / Sunday
        day += timedelta(days=1)
    naive_local = datetime(day.year, day.month, day.day, hour, minute)
    return naive_local.replace(tzinfo=LOCAL_TZ).astimezone(timezone.utc)
