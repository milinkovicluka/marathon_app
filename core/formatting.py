from datetime import timedelta


def format_pace(pace: timedelta | None) -> str:
    if pace is None:
        return "n/a"
    seconds = round(pace.total_seconds())
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes}:{seconds:02d}/km"
