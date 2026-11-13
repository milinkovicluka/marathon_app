from datetime import date, timedelta
import pytest
from core.models import Activity
from core.storage import Storage


def make_run(date: date = date(2026, 10, 30)) -> Activity:
    return Activity(
        date=date,
        type="run",
        distance_km=5.0,
        duration=timedelta(minutes=30),
    )


@pytest.fixture
def store(tmp_path):
    return Storage(tmp_path / "test.db")

def test_new_database_is_empty(store):
    assert store.list_activities() == []

def test_add_and_list(store):
    activity = make_run()
    saved = store.add(activity)
    assert saved.id is not None
    assert activity.id is None
    assert store.list_activities() == [saved]


def test_adding_same_activity_twice_does_not_change_input(store):
    activity = make_run()
    first_saved = store.add(activity)
    second_saved = store.add(activity)

    assert activity.id is None
    assert first_saved.id is not None
    assert second_saved.id is not None
    assert first_saved.id != second_saved.id
    assert len(store.list_activities()) == 2


def test_list_is_newest_first(store):
    store.add(make_run(date=date(2026, 11, 1)))
    store.add(make_run(date=date(2026, 11, 3)))
    dates = [a.date for a in store.list_activities()]
    assert dates == [date(2026, 11, 3), date(2026, 11, 1)]

def test_update(store):
    saved = store.add(make_run())
    saved.notes = "felt great"
    store.update(saved)
    assert store.list_activities()[0].notes == "felt great"

def test_delete(store):
    saved = store.add(make_run())
    store.delete(saved.id)
    assert store.list_activities() == []

def test_delete_missing_activity_raises(store):
    with pytest.raises(LookupError):
        store.delete(999)

def test_update_missing_activity_raises(store):
    activity = make_run()
    activity.id = 999
    with pytest.raises(LookupError):
        store.update(activity)

def test_data_survives_reopen(tmp_path):
    Storage(tmp_path / "test.db").add(make_run())
    assert len(Storage(tmp_path / "test.db").list_activities()) == 1

def _interval_run() -> Activity:
    from core.models import Segment

    return Activity(
        date=date(2026, 11, 5),
        type="run",
        distance_km=9.6,
        duration=timedelta(minutes=46),
        notes="intervals",
        segments=(
            Segment.from_pace(2, timedelta(minutes=4)),
            Segment.from_pace(1, timedelta(minutes=3, seconds=50)),
        ),
    )


def test_segments_are_saved_in_order_and_listed_back(store):
    saved = store.add(_interval_run())
    assert store.list_activities() == [saved]
    assert [segment.distance_km for segment in saved.segments] == [2, 1]


def test_update_replaces_segments_and_delete_removes_them(store):
    from dataclasses import replace

    saved = store.add(_interval_run())
    store.update(replace(saved, segments=saved.segments[:1]))
    assert store.list_activities()[0].segments == saved.segments[:1]

    store.delete(saved.id)
    other = store.add(make_run())
    assert store.list_activities() == [other]
    assert other.segments == ()


def test_existing_database_without_segments_table_still_loads(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL, type TEXT NOT NULL,
                distance_km REAL NOT NULL,
                duration_microseconds INTEGER NOT NULL, notes TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO activities (date, type, distance_km, duration_microseconds, notes)"
            " VALUES ('2026-11-01', 'run', 17.0, 4974000000, 'long run')"
        )
    [activity] = Storage(path).list_activities()
    assert activity.distance_km == 17.0
    assert activity.segments == ()


def test_source_id_is_saved_and_found(store):
    from dataclasses import replace

    saved = store.add(replace(make_run(), source_id="fit:2026-11-07T06:56:44+00:00"))
    assert store.has_source("fit:2026-11-07T06:56:44+00:00")
    assert not store.has_source("fit:other")
    assert store.list_activities()[0].source_id == saved.source_id


def test_same_source_cannot_be_saved_twice(store):
    import sqlite3
    from dataclasses import replace

    run = replace(make_run(), source_id="fit:x")
    store.add(run)
    with pytest.raises(sqlite3.IntegrityError):
        store.add(run)
