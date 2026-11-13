from pathlib import Path
from zoneinfo import ZoneInfo

from core import fit_import
from core.storage import Storage
from core.watch_import import find_watch_activity_dirs, import_from_watch, new_watch_files

PRAGUE = ZoneInfo("Europe/Prague")


def _watch(tmp_path: Path, files: dict[str, bytes]) -> Path:
    activity_dir = tmp_path / "Volumes" / "GARMIN" / "GARMIN" / "ACTIVITY"
    activity_dir.mkdir(parents=True)
    for name, content in files.items():
        (activity_dir / name).write_bytes(content)
    (tmp_path / "Volumes" / "Macintosh HD").mkdir()
    return activity_dir


def _fake_decode(monkeypatch, decoded):
    from datetime import datetime, timezone

    def decode(payload):
        decoded.append(payload)
        if payload == b"broken":
            raise ValueError("not a FIT file")
        day = int(payload.decode()[-1])
        return {
            "file_id_mesgs": [{"type": "activity", "garmin_product": "fenix5"}],
            "sport_mesgs": [{"name": "Run", "sport": "running"}],
            "session_mesgs": [{
                "start_time": datetime(2026, 11, day, 7, tzinfo=timezone.utc),
                "total_timer_time": 1800,
                "total_distance": 6000,
                "sport": "running",
            }],
        }

    monkeypatch.setattr(fit_import, "decode_fit", decode)


def test_finds_garmin_disk_among_volumes(tmp_path):
    activity_dir = _watch(tmp_path, {})
    assert find_watch_activity_dirs(tmp_path / "Volumes") == [activity_dir]
    assert find_watch_activity_dirs(tmp_path / "nowhere") == []


def test_each_watch_file_is_decoded_once_and_new_ones_later(tmp_path, monkeypatch):
    activity_dir = _watch(tmp_path, {"A1.FIT": b"run 1", "A2.FIT": b"run 2",
                                     "B.FIT": b"broken", "notes.txt": b"x"})
    decoded = []
    _fake_decode(monkeypatch, decoded)
    storage = Storage(tmp_path / "test.db")
    steps = []

    first = import_from_watch(storage, activity_dir, lambda d, t: steps.append((d, t)), PRAGUE)
    assert len(first.imported) == 2
    assert [path.name for path, _ in first.failed] == ["B.FIT"]
    assert steps[0] == (0, 3) and steps[-1] == (3, 3)

    (activity_dir / "A3.FIT").write_bytes(b"run 3")
    decoded.clear()
    second = import_from_watch(storage, activity_dir, local_zone=PRAGUE)
    # Only the new file and the one that failed are read again.
    assert sorted(decoded) == [b"broken", b"run 3"]
    assert len(second.imported) == 1
    assert [p.name for p in new_watch_files(storage, activity_dir)] == ["B.FIT"]
