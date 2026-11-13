"""Import straight from a Garmin watch plugged in over USB.

A Fenix 5 shows up on a Mac as a disk (e.g. /Volumes/GARMIN) with every
workout in GARMIN/ACTIVITY as a .FIT file. Files are only read, never
changed. Each file is decoded once; after that it is remembered by name
and size, so later imports only look at new workouts.
"""

from collections.abc import Callable
from datetime import tzinfo
from pathlib import Path

from core.fit_import import ImportResult, import_files
from core.storage import Storage

DEFAULT_VOLUMES = Path("/Volumes")


def find_watch_activity_dirs(volumes: Path = DEFAULT_VOLUMES) -> list[Path]:
    try:
        candidates = sorted(volumes.iterdir())
    except OSError:
        return []
    return [
        volume / "GARMIN" / "ACTIVITY"
        for volume in candidates
        if (volume / "GARMIN" / "ACTIVITY").is_dir()
    ]


def _file_key(path: Path) -> str:
    return f"{path.name}:{path.stat().st_size}"


def new_watch_files(storage: Storage, activity_dir: Path) -> list[Path]:
    files = sorted(
        path
        for path in activity_dir.iterdir()
        if path.suffix.lower() == ".fit" and not path.name.startswith(".")
    )
    return [path for path in files if not storage.has_device_file(_file_key(path))]


def import_from_watch(
    storage: Storage,
    activity_dir: Path,
    progress: Callable[[int, int], None] | None = None,
    local_zone: tzinfo | None = None,
) -> ImportResult:
    result = ImportResult()
    files = new_watch_files(storage, activity_dir)
    for done, path in enumerate(files):
        if progress is not None:
            progress(done, len(files))
        single = import_files(storage, [path], local_zone)
        result.imported += single.imported
        result.already_imported += single.already_imported
        result.possible_duplicates += single.possible_duplicates
        result.failed += single.failed
        if not single.failed:
            # Failed files are tried again next time.
            storage.mark_device_file(_file_key(path))
    if progress is not None:
        progress(len(files), len(files))
    return result
