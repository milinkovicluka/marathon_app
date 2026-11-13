from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pytest

from core import strava
from core.models import Activity
from core.storage import Storage
from core.strava import StravaSettings, activity_from_strava, sync

PRAGUE = ZoneInfo("Europe/Prague")


def _summary(name="Morning Trail Run", sport="TrailRun", start="2026-11-07T06:56:44Z",
             distance=8664.6, moving=3445, elapsed=3503):
    return {
        "id": 1,
        "name": name,
        "sport_type": sport,
        "start_date": start,
        "start_date_local": "2026-11-07T07:56:44Z",
        "distance": distance,
        "moving_time": moving,
        "elapsed_time": elapsed,
    }


class FakeStrava:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []
        self.refreshed = 0

    def __call__(self, method, url, fields, token):
        self.calls.append((method, url, dict(fields), token))
        if url == strava.TOKEN_URL:
            self.refreshed += 1
            return {"access_token": "new", "refresh_token": "r2", "expires_at": 2_000_000_000}
        page = fields["page"]
        return self.pages[page - 1] if page <= len(self.pages) else []


def _settings(**overrides):
    values = dict(client_id="1", client_secret="s", refresh_token="r1",
                  access_token="old", expires_at=0)
    values.update(overrides)
    return StravaSettings(**values)


def test_trail_run_summary_becomes_run_with_moving_time_and_same_id_as_fit():
    activity = activity_from_strava(_summary(), PRAGUE)
    assert activity.type == "run"
    assert activity.date == date(2026, 11, 7)
    assert activity.distance_km == pytest.approx(8.6646)
    assert activity.duration == timedelta(seconds=3445)
    assert activity.notes == "Morning Trail Run"
    assert activity.segments == ()
    # Same key as the FIT import of this run, so it is not added twice.
    assert activity.source_id == "start:2026-11-07T06:56:44+00:00"


@pytest.mark.parametrize(
    ("sport", "expected"),
    [("Run", "run"), ("VirtualRide", "bike"), ("WeightTraining", "gym"),
     ("TableTennis", "sport"), ("Swim", "sport")],
)
def test_strava_sport_types_map_to_app_types(sport, expected):
    assert activity_from_strava(_summary(sport=sport), PRAGUE).type == expected


def test_expired_token_is_refreshed_and_kept_fresh_one_is_reused():
    settings = _settings()
    fake = FakeStrava([])
    assert strava.fresh_access_token(settings, fake, now=1_000) == "new"
    assert settings.refresh_token == "r2"
    assert strava.fresh_access_token(settings, fake, now=1_000) == "new"
    assert fake.refreshed == 1


def test_sync_pages_through_history_skips_known_and_remembers_progress(tmp_path):
    storage = Storage(tmp_path / "test.db")
    page_one = [_summary(start=f"2026-11-0{day}T06:00:00Z", name=f"Run {day}")
                for day in (1, 2)]
    page_two = [_summary(start="2026-11-05T06:00:00Z", sport="TableTennis",
                         name="Pingpong", distance=0, moving=3600)]
    fake = FakeStrava([page_one, page_two])
    settings = _settings()

    first = sync(storage, settings, fake, PRAGUE)
    assert [a.notes for a in first.imported] == ["Run 1", "Run 2", "Pingpong"]
    assert settings.synced_until == 1_793_858_400  # 2026-11-05 06:00 UTC
    list_calls = [call for call in fake.calls if call[1] == strava.ACTIVITIES_URL]
    assert [call[2]["after"] for call in list_calls] == [0, 0, 0]
    assert all(call[3] == "new" for call in list_calls)

    second = sync(storage, settings, FakeStrava([page_one]), PRAGUE)
    assert second.imported == []
    assert len(second.already_imported) == 2
    assert len(storage.list_activities()) == 3


def test_sync_flags_hand_logged_twin(tmp_path):
    storage = Storage(tmp_path / "test.db")
    by_hand = storage.add(Activity(date=date(2026, 11, 7), type="run",
                                   distance_km=8.6, duration=timedelta(minutes=57)))
    result = sync(storage, _settings(), FakeStrava([[_summary()]]), PRAGUE)
    assert [old.id for _new, old in result.possible_duplicates] == [by_hand.id]


def test_settings_round_trip_is_private(tmp_path):
    path = tmp_path / "strava.json"
    _settings(synced_until=5).save(path)
    loaded = StravaSettings.load(path)
    assert loaded.connected and loaded.synced_until == 5
    assert path.stat().st_mode & 0o077 == 0
    assert not StravaSettings.load(tmp_path / "missing.json").connected


def test_authorize_url_asks_for_activity_read_on_localhost():
    url = strava.authorize_url("123")
    assert "client_id=123" in url
    assert "scope=activity%3Aread_all" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fstrava" in url
