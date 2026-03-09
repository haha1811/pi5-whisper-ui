"""工具函式。

包含資料夾初始化、檔案命名、記錄器設定與 subprocess 執行輔助。
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


def ensure_dir(path: Path) -> Path:
    """確保資料夾存在。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_job_dir(output_root: Path, original_name: str) -> Path:
    """建立本次任務專屬目錄，避免不同任務檔案互相覆蓋。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_stem = Path(original_name).stem.replace(" ", "_")
    return ensure_dir(output_root / f"{safe_stem}_{timestamp}")


def setup_logger(log_file: Path) -> logging.Logger:
    """設定 logger：同時輸出到檔案，讓 UI 可以即時讀取顯示。"""
    logger_name = f"pi5_whisper_ui_{log_file.stem}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # 避免重複加 handler
    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def read_log_tail(log_file: Path, max_lines: int = 200) -> str:
    """讀取 log 末端內容，供 UI 顯示。"""
    if not log_file.exists():
        return "尚未產生 log。"
    lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(lines[-max_lines:])


def run_command(
    cmd: List[str],
    logger: logging.Logger,
    step_name: str,
    cwd: Path | None = None,
) -> Tuple[bool, str]:
    """執行外部指令，並將 stdout/stderr 寫入 log。"""
    logger.info("開始步驟：%s", step_name)
    logger.info("執行指令：%s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - 需完整回報錯誤給 UI
        msg = f"{step_name} 執行失敗：{exc}"
        logger.exception(msg)
        return False, msg

    if result.stdout:
        logger.info("%s stdout:\n%s", step_name, result.stdout.strip())
    if result.stderr:
        logger.info("%s stderr:\n%s", step_name, result.stderr.strip())

    if result.returncode != 0:
        msg = f"{step_name} 失敗，返回碼：{result.returncode}"
        logger.error(msg)
        return False, msg

    msg = f"{step_name} 完成"
    logger.info(msg)
    return True, msg
