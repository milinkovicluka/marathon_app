import sqlite3
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Generator, cast

from core.models import Activity, ActivityType


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

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            yield connection

    def add(self, activity: Activity) -> Activity:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO activities (
                    date, type, distance_km, duration_microseconds, notes
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    activity.date.isoformat(),
                    activity.type,
                    activity.distance_km,
                    activity.duration // timedelta(microseconds=1),
                    activity.notes,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an activity id")
            saved_activity = replace(activity, id=cursor.lastrowid)
        return saved_activity

    def list_activities(self) -> list[Activity]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, date, type, distance_km, duration_microseconds, notes
                FROM activities
                ORDER BY date DESC, id DESC
                """
            ).fetchall()

        return [
            Activity(
                id=row[0],
                date=date.fromisoformat(row[1]),
                type=cast(ActivityType, row[2]),
                distance_km=row[3],
                duration=timedelta(microseconds=row[4]),
                notes=row[5],
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
                    duration_microseconds = ?, notes = ?
                WHERE id = ?
                """,
                (
                    activity.date.isoformat(),
                    activity.type,
                    activity.distance_km,
                    activity.duration // timedelta(microseconds=1),
                    activity.notes,
                    activity.id,
                ),
            )
            if cursor.rowcount == 0:
                raise LookupError(f"activity with id {activity.id} does not exist")

    def delete(self, activity_id: int) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM activities WHERE id = ?",
                (activity_id,),
            )
            if cursor.rowcount == 0:
                raise LookupError(f"activity with id {activity_id} does not exist")