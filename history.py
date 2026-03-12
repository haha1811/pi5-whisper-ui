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
    audio_duration_seconds: float
    model: str
    language: str
    threads_used: int
    processing_time_seconds: float
    rtf: float
    cpu_logical_cores: int
    output_directory: str


class HistoryStore:
    def __init__(self, db_path: Path = CONFIG.history_db_path) -> None:
        self.db_path = db_path
        ensure_dir(self.db_path.parent)
        self._init_db()
        self._migrate_schema_if_needed()

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
                    audio_duration_seconds REAL NOT NULL DEFAULT 0,
                    model TEXT NOT NULL,
                    language TEXT NOT NULL,
                    threads_used INTEGER NOT NULL DEFAULT 1,
                    processing_time_seconds REAL NOT NULL DEFAULT 0,
                    rtf REAL NOT NULL DEFAULT 0,
                    cpu_logical_cores INTEGER NOT NULL DEFAULT 1,
                    output_directory TEXT NOT NULL
                )
                """
            )

    def _migrate_schema_if_needed(self) -> None:
        """舊版欄位相容：若缺欄位就補上，避免舊 DB 造成頁面 crash。"""
        with self._connect() as conn:
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(history)").fetchall()
            }

            # 舊版欄位名稱相容策略：audio_duration/threads/processing_time
            # 新增並統一到 *_seconds / threads_used。
            if "audio_duration_seconds" not in cols:
                conn.execute("ALTER TABLE history ADD COLUMN audio_duration_seconds REAL NOT NULL DEFAULT 0")
            if "threads_used" not in cols:
                conn.execute("ALTER TABLE history ADD COLUMN threads_used INTEGER NOT NULL DEFAULT 1")
            if "processing_time_seconds" not in cols:
                conn.execute("ALTER TABLE history ADD COLUMN processing_time_seconds REAL NOT NULL DEFAULT 0")
            if "rtf" not in cols:
                conn.execute("ALTER TABLE history ADD COLUMN rtf REAL NOT NULL DEFAULT 0")
            if "cpu_logical_cores" not in cols:
                conn.execute("ALTER TABLE history ADD COLUMN cpu_logical_cores INTEGER NOT NULL DEFAULT 1")

            # 若舊欄位存在，將資料補到新欄位（只在新欄位為預設值時覆蓋）。
            if "audio_duration" in cols:
                conn.execute(
                    """
                    UPDATE history
                    SET audio_duration_seconds = audio_duration
                    WHERE audio_duration_seconds = 0
                    """
                )
            if "threads" in cols:
                conn.execute(
                    """
                    UPDATE history
                    SET threads_used = threads
                    WHERE threads_used = 1
                    """
                )
            if "processing_time" in cols:
                conn.execute(
                    """
                    UPDATE history
                    SET processing_time_seconds = processing_time
                    WHERE processing_time_seconds = 0
                    """
                )

            # 若 rtf 尚未計算，補算一次。
            conn.execute(
                """
                UPDATE history
                SET rtf = CASE
                    WHEN audio_duration_seconds > 0 THEN processing_time_seconds / audio_duration_seconds
                    ELSE 0
                END
                WHERE rtf = 0
                """
            )

    def add_record(
        self,
        filename: str,
        audio_duration_seconds: float,
        model: str,
        language: str,
        threads_used: int,
        processing_time_seconds: float,
        rtf: float,
        cpu_logical_cores: int,
        output_directory: Path,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO history (
                    timestamp,
                    filename,
                    audio_duration_seconds,
                    model,
                    language,
                    threads_used,
                    processing_time_seconds,
                    rtf,
                    cpu_logical_cores,
                    output_directory
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(timespec="seconds"),
                    filename,
                    audio_duration_seconds,
                    model,
                    language,
                    threads_used,
                    processing_time_seconds,
                    rtf,
                    cpu_logical_cores,
                    str(output_directory),
                ),
            )

    def list_records(self) -> List[HistoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    timestamp,
                    filename,
                    audio_duration_seconds,
                    model,
                    language,
                    threads_used,
                    processing_time_seconds,
                    rtf,
                    cpu_logical_cores,
                    output_directory
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
                SELECT
                    id,
                    timestamp,
                    filename,
                    audio_duration_seconds,
                    model,
                    language,
                    threads_used,
                    processing_time_seconds,
                    rtf,
                    cpu_logical_cores,
                    output_directory
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
