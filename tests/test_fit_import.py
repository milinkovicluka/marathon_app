import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core import fit_import
from core.fit_import import activity_from_messages, import_files, read_fit_payloads
from core.storage import Storage

PRAGUE = ZoneInfo("Europe/Prague")
SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _lap(km, seconds, trigger="distance", **extra):
    return {
        "total_distance": km * 1000,
        "total_timer_time": seconds,
        "lap_trigger": trigger,
        **extra,
    }


def _messages(sport="running", laps=(), name=["Trail Run", "", "\x05 "], start=None):
    # Shaped like the Fenix 5 trail run of 7 Nov 2026.
    return {
        "file_id_mesgs": [{"type": "activity", "garmin_product": "fenix5"}],
        "sport_mesgs": [{"name": name, "sport": sport}],
        "session_mesgs": [
            {
                "start_time": start
                or datetime(2026, 11, 7, 6, 56, 44, tzinfo=timezone.utc),
                "total_timer_time": 3445.302,
                "total_elapsed_time": 3503.276,
                "total_distance": 8664.64,
                "sport": sport,
            }
        ],
        "lap_mesgs": list(laps),
    }


def test_run_summary_uses_moving_time_and_local_date():
    activity = activity_from_messages(_messages(), PRAGUE)
    assert activity.type == "run"
    assert activity.date == date(2026, 11, 7)
    assert activity.distance_km == pytest.approx(8.66464)
    assert activity.duration == timedelta(seconds=3445)
    assert activity.notes == "Trail Run (Fenix 5)"
    assert activity.source_id == "start:2026-11-07T06:56:44+00:00"


def test_evening_run_in_utc_lands_on_local_day():
    late = datetime(2026, 11, 11, 23, 30, tzinfo=timezone.utc)
    activity = activity_from_messages(_messages(start=late), PRAGUE)
    assert activity.date == date(2026, 11, 12)


def test_auto_km_laps_are_not_segments_but_manual_laps_are():
    laps = [
        _lap(1, 326),
        _lap(1, 323),
        _lap(2, 480, trigger="manual"),
        _lap(1, 230, trigger="manual"),
        _lap(0.66, 213, trigger="session_end"),
    ]
    activity = activity_from_messages(_messages(laps=laps), PRAGUE)
    assert [(s.distance_km, s.duration) for s in activity.segments] == [
        (2, timedelta(minutes=8)),
        (1, timedelta(seconds=230)),
    ]


def test_active_workout_steps_are_segments_recovery_is_not():
    laps = [
        _lap(1.5, 540, trigger="session_end", wkt_step_index=0, intensity="warmup"),
        _lap(1, 235, trigger="session_end", wkt_step_index=1, intensity="active"),
        _lap(0.3, 120, trigger="session_end", wkt_step_index=2, intensity="recovery"),
    ]
    activity = activity_from_messages(_messages(laps=laps), PRAGUE)
    assert [s.distance_km for s in activity.segments] == [1]


@pytest.mark.parametrize(
    ("sport", "expected"),
    [("running", "run"), ("cycling", "bike"), ("training", "gym"), ("swimming", "sport")],
)
def test_sport_maps_to_activity_type(sport, expected):
    assert activity_from_messages(_messages(sport=sport), PRAGUE).type == expected


def test_non_run_types_get_no_segments_and_caps_names_are_tidied():
    messages = _messages(
        sport="swimming", laps=[_lap(1, 300, trigger="manual")], name="INDOOR"
    )
    activity = activity_from_messages(messages, PRAGUE)
    assert activity.segments == ()
    assert activity.notes == "Indoor (Fenix 5)"


def test_file_without_session_is_rejected():
    messages = _messages()
    messages["session_mesgs"] = []
    with pytest.raises(ValueError, match="no activity summary"):
        activity_from_messages(messages, PRAGUE)


def test_zip_from_garmin_connect_is_opened(tmp_path):
    archive_path = tmp_path / "activity.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("123_ACTIVITY.fit", b"fit bytes")
    assert read_fit_payloads(archive_path) == [b"fit bytes"]


def test_import_skips_already_imported_and_reports_bad_files(tmp_path, monkeypatch):
    good = tmp_path / "run.fit"
    good.write_bytes(b"run")
    bad = tmp_path / "notes.txt"
    bad.write_bytes(b"not fit")

    def fake_decode(payload):
        if payload != b"run":
            raise ValueError("not a FIT file")
        return _messages()

    monkeypatch.setattr(fit_import, "decode_fit", fake_decode)
    storage = Storage(tmp_path / "test.db")

    first = import_files(storage, [good, bad], PRAGUE)
    second = import_files(storage, [good], PRAGUE)

    assert len(first.imported) == 1
    assert first.failed == [(bad, "not a FIT file")]
    assert second.imported == []
    assert second.already_imported == [good]
    assert len(storage.list_activities()) == 1


@pytest.mark.skipif(
    not any(SAMPLES.glob("*.fit")), reason="no private sample files in samples/"
)
def test_real_garmin_samples_import(tmp_path):
    result = import_files(Storage(tmp_path / "test.db"), sorted(SAMPLES.glob("*.fit")))
    assert result.failed == []
    assert result.imported
    for activity in result.imported:
        assert activity.distance_km > 0
        assert activity.duration > timedelta(0)


def test_hand_logged_entry_of_same_workout_is_flagged(tmp_path, monkeypatch):
    from core.models import Activity

    fit_file = tmp_path / "run.fit"
    fit_file.write_bytes(b"run")
    monkeypatch.setattr(fit_import, "decode_fit", lambda payload: _messages())
    storage = Storage(tmp_path / "test.db")
    by_hand = storage.add(
        Activity(date=date(2026, 11, 7), type="run", distance_km=8.6,
                 duration=timedelta(minutes=57))
    )
    storage.add(
        Activity(date=date(2026, 11, 7), type="run", distance_km=3.0,
                 duration=timedelta(minutes=15), notes="evening shakeout")
    )

    result = import_files(storage, [fit_file], PRAGUE)

    assert [(new.source_id, old.id) for new, old in result.possible_duplicates] == [
        ("start:2026-11-07T06:56:44+00:00", by_hand.id)
    ]
