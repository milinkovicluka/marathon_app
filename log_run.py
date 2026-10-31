import argparse
import math
from datetime import date, timedelta

from core.countdown import format_countdown, time_until_race
from core.formatting import format_pace
from core.models import Activity
from core.paths import DATABASE_PATH
from core.stats import km_in_week
from core.storage import Storage


def _non_negative_number(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite non-negative number")
    return number

def main() -> None:
    parser = argparse.ArgumentParser(description="Log a run.")
    parser.add_argument("distance_km", type=_non_negative_number, help="distance in km")
    parser.add_argument("minutes", type=_non_negative_number, help="duration in minutes")
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    run_date = args.date or date.today()

    activity = Activity(
        date=run_date,
        type="run",
        distance_km=args.distance_km,
        duration=timedelta(minutes=args.minutes),
        notes=args.notes,
    )
    storage = Storage(DATABASE_PATH)
    storage.add(activity)

    activities = storage.list_activities()
    print(
        f"Saved: {activity.distance_km:.1f} km in {args.minutes:g} min "
        f"({format_pace(activity.pace)})"
    )
    print(
        f"This week: {km_in_week(activities, run_date):.1f} km "
        f"· 🏃 {format_countdown(time_until_race())} to go"
    )


if __name__ == "__main__":
    main()
