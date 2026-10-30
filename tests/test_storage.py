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

def test_data_survives_reopen(tmp_path):
    Storage(tmp_path / "test.db").add(make_run())
    assert len(Storage(tmp_path / "test.db").list_activities()) == 1