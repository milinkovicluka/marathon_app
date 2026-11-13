from pathlib import Path

DATABASE_PATH = Path(__file__).resolve().parent.parent / "activities.db"
# Strava app keys and login tokens; private, ignored by git.
STRAVA_SETTINGS_PATH = DATABASE_PATH.parent / "strava.json"
