"""Turn Garmin .fit files (or the .zip Garmin Connect exports) into activities."""

import re
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

from garmin_fit_sdk import Decoder, Stream

from core.models import SEGMENT_TYPES, Activity, ActivityType, Segment
from core.storage import Storage

FitMessages = Mapping[str, Sequence[Mapping[str, Any]]]

_TYPE_BY_SPORT: dict[str, ActivityType] = {
    "running": "run",
    "cycling": "bike",
    "e_biking": "bike",
    "training": "gym",
}


def read_fit_payloads(path: str | Path) -> list[bytes]:
    """Return the raw bytes of a .fit file, or of every .fit inside a .zip."""
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = sorted(
                name for name in archive.namelist() if name.lower().endswith(".fit")
            )
            if not names:
                raise ValueError(f"{path.name} has no .fit file inside")
            return [archive.read(name) for name in names]
    return [path.read_bytes()]


def decode_fit(payload: bytes) -> FitMessages:
    decoder = Decoder(Stream.from_byte_array(bytearray(payload)))
    if not decoder.is_fit():
        raise ValueError("not a FIT file")
    messages, errors = decoder.read()
    if errors:
        raise ValueError(f"can't read FIT file: {errors[0]}")
    return messages


def _text(value: Any) -> str:
    # Some watches (e.g. Fenix 5) store the name as a list of strings.
    if isinstance(value, list):
        value = next((item for item in value if isinstance(item, str) and item), "")
    return value.strip() if isinstance(value, str) else ""


def _activity_name(messages: FitMessages, session: Mapping[str, Any]) -> str:
    sport_messages = messages.get("sport_mesgs") or [{}]
    name = _text(sport_messages[0].get("name"))
    if name.isupper():
        name = name.title()
    if not name:
        name = str(session.get("sport", "activity")).replace("_", " ").capitalize()
    file_ids = messages.get("file_id_mesgs") or [{}]
    product = file_ids[0].get("garmin_product")
    if isinstance(product, str):
        device = re.sub(r"(?<=[a-z])(?=\d)", " ", product).replace("_", " ").title()
        name = f"{name} ({device})"
    return name


def _is_segment_lap(lap: Mapping[str, Any]) -> bool:
    """Manual laps and active workout steps are segments; auto km laps are not."""
    if not lap.get("total_distance") or not lap.get("total_timer_time"):
        return False
    if lap.get("lap_trigger") == "manual":
        return True
    return lap.get("wkt_step_index") is not None and lap.get("intensity") == "active"


def activity_from_messages(messages: FitMessages, local_zone: tzinfo | None = None) -> Activity:
    file_ids = messages.get("file_id_mesgs") or []
    if file_ids and file_ids[0].get("type") not in (None, "activity"):
        raise ValueError(f"not an activity file ({file_ids[0].get('type')})")
    sessions = messages.get("session_mesgs") or []
    if not sessions:
        raise ValueError("no activity summary in the file")
    session = sessions[0]

    start: datetime = session["start_time"]
    activity_type = _TYPE_BY_SPORT.get(str(session.get("sport")), "sport")
    segments: tuple[Segment, ...] = ()
    if activity_type in SEGMENT_TYPES:
        segments = tuple(
            Segment(
                distance_km=lap["total_distance"] / 1000,
                duration=timedelta(seconds=round(lap["total_timer_time"])),
            )
            for lap in messages.get("lap_mesgs") or []
            if _is_segment_lap(lap)
        )
    return Activity(
        date=start.astimezone(local_zone).date(),
        type=activity_type,
        distance_km=(session.get("total_distance") or 0) / 1000,
        duration=timedelta(seconds=round(session.get("total_timer_time") or 0)),
        notes=_activity_name(messages, session),
        segments=segments,
        source_id=f"fit:{start.isoformat()}",
    )


@dataclass
class ImportResult:
    imported: list[Activity] = field(default_factory=list)
    already_imported: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    # (imported, existing hand-logged entry that looks like the same workout)
    possible_duplicates: list[tuple[Activity, Activity]] = field(default_factory=list)


def _looks_like_same_workout(imported: Activity, logged: Activity) -> bool:
    if logged.source_id is not None:
        return False
    if (logged.date, logged.type) != (imported.date, imported.type):
        return False
    tolerance = max(0.3, imported.distance_km * 0.05)
    return abs(logged.distance_km - imported.distance_km) <= tolerance


def import_files(
    storage: Storage, paths: Sequence[str | Path], local_zone: tzinfo | None = None
) -> ImportResult:
    result = ImportResult()
    existing = storage.list_activities()
    for path in map(Path, paths):
        try:
            activities = [
                activity_from_messages(decode_fit(payload), local_zone)
                for payload in read_fit_payloads(path)
            ]
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
            result.failed.append((path, str(error)))
            continue
        for activity in activities:
            if storage.has_source(activity.source_id or ""):
                result.already_imported.append(path)
            else:
                saved = storage.add(activity)
                result.imported.append(saved)
                result.possible_duplicates.extend(
                    (saved, logged)
                    for logged in existing
                    if _looks_like_same_workout(saved, logged)
                )
    return result
