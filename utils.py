"""工具函式。"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_job_dir(output_root: Path, original_name: str) -> Path:
    """建立任務專屬目錄，避免同秒啟動衝突。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_stem = Path(original_name).stem.replace(" ", "_")
    unique = uuid.uuid4().hex[:6]
    return ensure_dir(output_root / f"{safe_stem}_{timestamp}_{unique}")


def setup_logger(log_file: Path) -> logging.Logger:
    logger_name = f"pi5_whisper_ui_{log_file.stem}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def read_log_tail(log_file: Path, max_lines: int = 200) -> str:
    if not log_file.exists():
        return "尚未產生 log。"
    lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(lines[-max_lines:])


def run_command(
    cmd: List[str],
    logger: logging.Logger,
    step_name: str,
    cwd: Path | None = None,
    on_output: Optional[Callable[[str], None]] = None,
    on_start: Optional[Callable[[int], None]] = None,
    on_heartbeat: Optional[Callable[[], None]] = None,
    heartbeat_interval_sec: float = 2.0,
) -> Tuple[bool, str]:
    """執行外部指令，支援輸出串流與 heartbeat。"""
    logger.info("開始步驟：%s", step_name)
    logger.info("執行指令：%s", " ".join(cmd))

    try:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:  # noqa: BLE001
        msg = f"{step_name} 執行失敗：{exc}"
        logger.exception(msg)
        return False, msg

    if on_start:
        on_start(process.pid)

    stop_flag = threading.Event()

    def heartbeat_worker() -> None:
        while not stop_flag.is_set():
            if on_heartbeat:
                on_heartbeat()
            stop_flag.wait(max(0.5, heartbeat_interval_sec))

    hb_thread = threading.Thread(target=heartbeat_worker, daemon=True)
    hb_thread.start()

    try:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            if line:
                logger.info("%s output: %s", step_name, line)
                if on_output:
                    on_output(line)
    finally:
        stop_flag.set()
        hb_thread.join(timeout=1.0)

    return_code = process.wait()
    if return_code != 0:
        msg = f"{step_name} 失敗，返回碼：{return_code}"
        logger.error(msg)
        return False, msg

    msg = f"{step_name} 完成"
    logger.info(msg)
    return True, msg


def format_seconds(seconds: float) -> str:
    total = int(max(0, round(seconds)))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {sec}s"
    return f"{minutes}m {sec}s"


def get_dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


def format_bytes(num: int) -> str:
    size = float(num)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{num} B"
