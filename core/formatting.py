from datetime import timedelta


def format_pace(pace: timedelta | None) -> str:
    if pace is None:
        return "n/a"
    seconds = round(pace.total_seconds())
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes}:{seconds:02d}/km"


def format_duration(duration: timedelta) -> str:
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"
