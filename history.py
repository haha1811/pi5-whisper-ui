"""使用紀錄儲存（SQLite）。"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from config import CONFIG
from utils import ensure_dir


@dataclass
class HistoryRecord:
    id: int
    timestamp: str
    filename: str
    audio_duration: float
    model: str
    language: str
    threads: int
    processing_time: float
    output_directory: str


class HistoryStore:
    def __init__(self, db_path: Path = CONFIG.history_db_path) -> None:
        self.db_path = db_path
        ensure_dir(self.db_path.parent)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    audio_duration REAL NOT NULL,
                    model TEXT NOT NULL,
                    language TEXT NOT NULL,
                    threads INTEGER NOT NULL,
                    processing_time REAL NOT NULL,
                    output_directory TEXT NOT NULL
                )
                """
            )

    def add_record(
        self,
        filename: str,
        audio_duration: float,
        model: str,
        language: str,
        threads: int,
        processing_time: float,
        output_directory: Path,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO history (timestamp, filename, audio_duration, model, language, threads, processing_time, output_directory)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(timespec="seconds"),
                    filename,
                    audio_duration,
                    model,
                    language,
                    threads,
                    processing_time,
                    str(output_directory),
                ),
            )

    def list_records(self) -> List[HistoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, filename, audio_duration, model, language, threads, processing_time, output_directory
                FROM history
                ORDER BY id DESC
                """
            ).fetchall()
        return [HistoryRecord(*row) for row in rows]

    def delete_record(self, record_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM history WHERE id = ?", (record_id,))

    def get_record(self, record_id: int) -> HistoryRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, timestamp, filename, audio_duration, model, language, threads, processing_time, output_directory
                FROM history
                WHERE id = ?
                """,
                (record_id,),
            ).fetchone()
        return HistoryRecord(*row) if row else None

    def delete_record_and_output(self, record_id: int) -> None:
        record = self.get_record(record_id)
        if record:
            output_dir = Path(record.output_directory)
            if output_dir.exists():
                shutil.rmtree(output_dir, ignore_errors=True)
        self.delete_record(record_id)

    def cleanup_older_than_days(self, days: int, delete_outputs: bool = True) -> int:
        cutoff = datetime.now() - timedelta(days=max(0, days))
        deleted = 0
        for record in self.list_records():
            try:
                ts = datetime.fromisoformat(record.timestamp)
            except ValueError:
                continue
            if ts < cutoff:
                if delete_outputs:
                    output_dir = Path(record.output_directory)
                    if output_dir.exists():
                        shutil.rmtree(output_dir, ignore_errors=True)
                self.delete_record(record.id)
                deleted += 1
        return deleted
