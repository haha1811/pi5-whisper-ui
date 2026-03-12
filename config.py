"""全域設定檔。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class AppConfig:
    """應用程式設定。"""

    project_root: Path = Path("/mnt/ssd/workspace/pi5-whisper-ui")

    # 工具路徑
    whisper_cpp_root: Path = Path("/mnt/ssd/tools/whisper.cpp")
    models_root: Path = Path("/mnt/ssd/tools/whisper.cpp/models")
    ffmpeg_binary: str = "ffmpeg"

    # 資料路徑
    output_root: Path = Path("/mnt/ssd/workspace/pi5-whisper-ui/outputs")
    log_root: Path = Path("/mnt/ssd/workspace/pi5-whisper-ui/logs")
    data_root: Path = Path("/mnt/ssd/workspace/pi5-whisper-ui/data")
    history_db_path: Path = Path("/mnt/ssd/workspace/pi5-whisper-ui/data/history.db")
    current_job_state_path: Path = Path("/mnt/ssd/workspace/pi5-whisper-ui/data/current_job.json")

    # 轉寫預設
    default_segment_minutes: int = 15
    default_model_name: str = "small"
    default_language: str = "zh"
    default_threads: int = 4

    # 系統監控
    enable_system_monitor: bool = True
    stale_running_job_seconds: int = 900


CONFIG = AppConfig()

MODEL_PATHS: Dict[str, Path] = {
    "small": CONFIG.models_root / "ggml-small.bin",
    "medium": CONFIG.models_root / "ggml-medium.bin",
    "large-v3-turbo": CONFIG.models_root / "ggml-large-v3-turbo.bin",
}

LANGUAGE_OPTIONS: List[str] = ["auto", "zh", "en", "ja"]

WHISPER_CANDIDATES = [
    CONFIG.whisper_cpp_root / "build/bin/whisper-cli",
    CONFIG.whisper_cpp_root / "whisper-cli",
    CONFIG.whisper_cpp_root / "build/bin/main",
    CONFIG.whisper_cpp_root / "main",
]
