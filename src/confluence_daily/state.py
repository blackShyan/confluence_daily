from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
import sqlite3
from collections.abc import Iterator

from .config import app_data_dir


class DailyState:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_dir() / "state.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def mark_uploaded(self, work_date: date, page_id: str, page_url: str | None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO uploads(date, page_id, page_url, uploaded_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    page_id = excluded.page_id,
                    page_url = excluded.page_url,
                    uploaded_at = excluded.uploaded_at
                """,
                (work_date.isoformat(), page_id, page_url, datetime.now().isoformat(timespec="seconds")),
            )

    def is_uploaded(self, work_date: date) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM uploads WHERE date = ?",
                (work_date.isoformat(),),
            ).fetchone()
        return row is not None

    def mark_completed_without_upload(self, work_date: date) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO reminders(date, completed, last_notified_at, snooze_until)
                VALUES (?, 1, ?, NULL)
                ON CONFLICT(date) DO UPDATE SET
                    completed = 1,
                    last_notified_at = excluded.last_notified_at,
                    snooze_until = NULL
                """,
                (work_date.isoformat(), datetime.now().isoformat(timespec="seconds")),
            )

    def is_completed_without_upload(self, work_date: date) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT completed FROM reminders WHERE date = ?",
                (work_date.isoformat(),),
            ).fetchone()
        return bool(row and row[0])

    def set_snooze_until(self, work_date: date, when: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO reminders(date, completed, last_notified_at, snooze_until)
                VALUES (?, 0, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    completed = 0,
                    last_notified_at = excluded.last_notified_at,
                    snooze_until = excluded.snooze_until
                """,
                (
                    work_date.isoformat(),
                    datetime.now().isoformat(timespec="seconds"),
                    when.isoformat(timespec="seconds"),
                ),
            )

    def snooze_until(self, work_date: date) -> datetime | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT snooze_until FROM reminders WHERE date = ?",
                (work_date.isoformat(),),
            ).fetchone()
        if not row or not row[0]:
            return None
        return datetime.fromisoformat(row[0])

    def mark_notified(self, work_date: date) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO reminders(date, completed, last_notified_at, snooze_until)
                VALUES (?, 0, ?, NULL)
                ON CONFLICT(date) DO UPDATE SET
                    last_notified_at = excluded.last_notified_at,
                    snooze_until = NULL
                """,
                (work_date.isoformat(), datetime.now().isoformat(timespec="seconds")),
            )

    def last_notified_at(self, work_date: date) -> datetime | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT last_notified_at FROM reminders WHERE date = ?",
                (work_date.isoformat(),),
            ).fetchone()
        if not row or not row[0]:
            return None
        return datetime.fromisoformat(row[0])

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    date TEXT PRIMARY KEY,
                    page_id TEXT NOT NULL,
                    page_url TEXT,
                    uploaded_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    date TEXT PRIMARY KEY,
                    completed INTEGER NOT NULL DEFAULT 0,
                    last_notified_at TEXT,
                    snooze_until TEXT
                )
                """
            )
