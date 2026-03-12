"""使用紀錄儲存（SQLite）。"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List

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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


class HistoryStore:
    def __init__(self, db_path: Path = CONFIG.history_db_path) -> None:
        self.db_path = db_path
        ensure_dir(self.db_path.parent)
        self._init_db()
        self._migrate_schema_if_needed()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _get_columns(self, conn: sqlite3.Connection) -> set[str]:
        return {row[1] for row in conn.execute("PRAGMA table_info(history)").fetchall()}

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
            cols = self._get_columns(conn)

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

            # 重新讀取欄位，處理資料搬移
            cols = self._get_columns(conn)
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
        """寫入一筆使用紀錄。

        為了相容舊版 schema，若舊欄位（audio_duration/processing_time/threads）存在，
        也會同步寫入，避免 NOT NULL constraint 錯誤。
        """
        ad = _to_float(audio_duration_seconds, 0.0)
        pt = _to_float(processing_time_seconds, 0.0)
        rtf_value = _to_float(rtf, 0.0)
        th = _to_int(threads_used, 1)
        cores = _to_int(cpu_logical_cores, 1)

        with self._connect() as conn:
            cols = self._get_columns(conn)

            payload: dict[str, Any] = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "filename": filename or "unknown",
                "model": model or "unknown",
                "language": language or "unknown",
                "output_directory": str(output_directory),
            }

            # 新版欄位
            if "audio_duration_seconds" in cols:
                payload["audio_duration_seconds"] = ad
            if "threads_used" in cols:
                payload["threads_used"] = max(1, th)
            if "processing_time_seconds" in cols:
                payload["processing_time_seconds"] = max(0.0, pt)
            if "rtf" in cols:
                payload["rtf"] = max(0.0, rtf_value)
            if "cpu_logical_cores" in cols:
                payload["cpu_logical_cores"] = max(1, cores)

            # 舊版欄位（關鍵：避免舊 DB 的 NOT NULL 欄位 insert 失敗）
            if "audio_duration" in cols:
                payload["audio_duration"] = ad
            if "threads" in cols:
                payload["threads"] = max(1, th)
            if "processing_time" in cols:
                payload["processing_time"] = max(0.0, pt)

            columns = ", ".join(payload.keys())
            placeholders = ", ".join(["?"] * len(payload))
            values = tuple(payload.values())

            conn.execute(
                f"INSERT INTO history ({columns}) VALUES ({placeholders})",
                values,
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
