"""全域設定檔。

此檔案集中管理所有路徑與預設值，避免在其他檔案散落硬編碼路徑。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class AppConfig:
    """應用程式設定。"""

    # 專案在 Raspberry Pi 5 SSD 上的建議根目錄
    project_root: Path = Path("/mnt/ssd/workspace/pi5-whisper-ui")

    # 工具路徑
    whisper_cpp_root: Path = Path("/mnt/ssd/tools/whisper.cpp")
    models_root: Path = Path("/mnt/ssd/tools/whisper.cpp/models")
    ffmpeg_binary: str = "ffmpeg"

    # 輸出設定（避免寫入 SD 卡）
    output_root: Path = Path("/mnt/ssd/workspace/pi5-whisper-ui/outputs")
    log_root: Path = Path("/mnt/ssd/workspace/pi5-whisper-ui/logs")

    # 轉寫設定
    default_segment_minutes: int = 15
    default_model_name: str = "small"
    default_language: str = "zh"
    default_threads: int = 4


CONFIG = AppConfig()

# 僅列出正式可用模型。
MODEL_PATHS: Dict[str, Path] = {
    "small": CONFIG.models_root / "ggml-small.bin",
    "medium": CONFIG.models_root / "ggml-medium.bin",
    "large-v3-turbo": CONFIG.models_root / "ggml-large-v3-turbo.bin",
}

LANGUAGE_OPTIONS: List[str] = ["auto", "zh", "en", "ja"]

# whisper.cpp 執行檔候選：優先使用 whisper-cli，main 僅作為後備。
WHISPER_CANDIDATES = [
    CONFIG.whisper_cpp_root / "build/bin/whisper-cli",
    CONFIG.whisper_cpp_root / "whisper-cli",
    CONFIG.whisper_cpp_root / "build/bin/main",
    CONFIG.whisper_cpp_root / "main",
]
