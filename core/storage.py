import sqlite3
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Generator, cast

from core.models import Activity, ActivityType, Segment


class Storage:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = database_path
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    type TEXT NOT NULL,
                    distance_km REAL NOT NULL,
                    duration_microseconds INTEGER NOT NULL,
                    notes TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activity_id INTEGER NOT NULL REFERENCES activities(id),
                    position INTEGER NOT NULL,
                    distance_km REAL NOT NULL,
                    duration_microseconds INTEGER NOT NULL
                )
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(activities)")
            }
            if "source_id" not in columns:
                connection.execute("ALTER TABLE activities ADD COLUMN source_id TEXT")
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS activities_source_id
                ON activities(source_id) WHERE source_id IS NOT NULL
                """
            )

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            yield connection

    @staticmethod
    def _write_segments(
        connection: sqlite3.Connection, activity_id: int, activity: Activity
    ) -> None:
        connection.execute(
            "DELETE FROM segments WHERE activity_id = ?", (activity_id,)
        )
        connection.executemany(
            """
            INSERT INTO segments (
                activity_id, position, distance_km, duration_microseconds
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (
                    activity_id,
                    position,
                    segment.distance_km,
                    segment.duration // timedelta(microseconds=1),
                )
                for position, segment in enumerate(activity.segments)
            ],
        )

    def add(self, activity: Activity) -> Activity:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO activities (
                    date, type, distance_km, duration_microseconds, notes,
                    source_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    activity.date.isoformat(),
                    activity.type,
                    activity.distance_km,
                    activity.duration // timedelta(microseconds=1),
                    activity.notes,
                    activity.source_id,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an activity id")
            self._write_segments(connection, cursor.lastrowid, activity)
            saved_activity = replace(activity, id=cursor.lastrowid)
        return saved_activity

    def list_activities(self) -> list[Activity]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, date, type, distance_km, duration_microseconds, notes,
                    source_id
                FROM activities
                ORDER BY date DESC, id DESC
                """
            ).fetchall()
            segment_rows = connection.execute(
                """
                SELECT activity_id, distance_km, duration_microseconds
                FROM segments
                ORDER BY activity_id, position
                """
            ).fetchall()

        segments_by_activity: dict[int, list[Segment]] = {}
        for activity_id, distance_km, duration_microseconds in segment_rows:
            segments_by_activity.setdefault(activity_id, []).append(
                Segment(
                    distance_km=distance_km,
                    duration=timedelta(microseconds=duration_microseconds),
                )
            )

        return [
            Activity(
                id=row[0],
                date=date.fromisoformat(row[1]),
                type=cast(ActivityType, row[2]),
                distance_km=row[3],
                duration=timedelta(microseconds=row[4]),
                notes=row[5],
                segments=tuple(segments_by_activity.get(row[0], ())),
                source_id=row[6],
            )
            for row in rows
        ]

    def update(self, activity: Activity) -> None:
        if activity.id is None:
            raise ValueError("activity must have an id to be updated")

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE activities
                SET date = ?, type = ?, distance_km = ?,
                    duration_microseconds = ?, notes = ?, source_id = ?
                WHERE id = ?
                """,
                (
                    activity.date.isoformat(),
                    activity.type,
                    activity.distance_km,
                    activity.duration // timedelta(microseconds=1),
                    activity.notes,
                    activity.source_id,
                    activity.id,
                ),
            )
            if cursor.rowcount == 0:
                raise LookupError(f"activity with id {activity.id} does not exist")
            self._write_segments(connection, activity.id, activity)

    def has_source(self, source_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM activities WHERE source_id = ?", (source_id,)
            ).fetchone()
        return row is not None

    def delete(self, activity_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM segments WHERE activity_id = ?", (activity_id,)
            )
            cursor = connection.execute(
                "DELETE FROM activities WHERE id = ?",
                (activity_id,),
            )
            if cursor.rowcount == 0:
                raise LookupError(f"activity with id {activity_id} does not exist")