from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

RACE_TIME_ZONE = ZoneInfo("Europe/Prague")
RACE_START_TIME = datetime(2027, 5, 2, 8, 0, tzinfo=RACE_TIME_ZONE)



def time_until_race(now: datetime | None = None) -> timedelta:
    """Return the absolute time remaining until the race starts."""
    if now is None:
        now = datetime.now(RACE_TIME_ZONE)

    return RACE_START_TIME.astimezone(timezone.utc) - now.astimezone(timezone.utc)


def format_countdown(remaining: timedelta) -> str:
    """Format the remaining time as days and hours, or a finish flag."""
    if remaining <= timedelta(0):
        return "🏁"

    hours = remaining.seconds // 3600
    return f"{remaining.days}d {hours}h"
