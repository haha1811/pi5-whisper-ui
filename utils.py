"""工具函式。"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple


def ensure_dir(path: Path) -> Path:
    """確保資料夾存在。"""
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_job_dir(output_root: Path, original_name: str) -> Path:
    """建立任務專屬目錄。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_stem = Path(original_name).stem.replace(" ", "_")
    return ensure_dir(output_root / f"{safe_stem}_{timestamp}")


def setup_logger(log_file: Path) -> logging.Logger:
    """設定 logger（寫檔）。"""
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
    """讀取 log 末端內容。"""
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
) -> Tuple[bool, str]:
    """執行外部指令（串流 log）。"""
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

    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.rstrip("\n")
        if line:
            logger.info("%s output: %s", step_name, line)
            if on_output:
                on_output(line)

    return_code = process.wait()
    if return_code != 0:
        msg = f"{step_name} 失敗，返回碼：{return_code}"
        logger.error(msg)
        return False, msg

    msg = f"{step_name} 完成"
    logger.info(msg)
    return True, msg
