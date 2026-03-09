"""逐字稿流程核心。

此模組負責：
1) m4a 轉 wav
2) wav 切段
3) 每段呼叫 whisper.cpp
4) 合併最終 txt
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from config import CONFIG, MODEL_PATHS, WHISPER_CANDIDATES
from utils import ensure_dir, make_job_dir, run_command, setup_logger

ProgressCallback = Callable[[str, int], None]


@dataclass
class TranscriptionResult:
    success: bool
    message: str
    final_txt_path: Optional[Path] = None
    log_file: Optional[Path] = None


class TranscriptionPipeline:
    """封裝整個轉寫流程，讓 UI 呼叫更簡潔。"""

    def __init__(self, output_root: Path | None = None, log_root: Path | None = None) -> None:
        self.output_root = ensure_dir(output_root or CONFIG.output_root)
        self.log_root = ensure_dir(log_root or CONFIG.log_root)

    @staticmethod
    def get_whisper_binary() -> Optional[Path]:
        """尋找 whisper.cpp 可執行檔。"""
        for candidate in WHISPER_CANDIDATES:
            if candidate.exists() and candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        return None

    @staticmethod
    def check_model_exists(model_name: str) -> tuple[bool, str]:
        """檢查模型是否存在。"""
        model_path = MODEL_PATHS.get(model_name)
        if model_path is None:
            return False, f"未知模型：{model_name}"
        if not model_path.exists():
            return False, f"模型不存在：{model_path}"
        return True, f"模型可用：{model_path}"

    @staticmethod
    def build_whisper_command(whisper_bin: Path, model_name: str, seg: Path, seg_txt_prefix: Path) -> List[str]:
        """建立 whisper.cpp 指令。

        whisper-cli 與 main 在本流程使用的參數（-m/-f/-of/-otxt/-nt）可相容。
        """
        return [
            str(whisper_bin),
            "-m",
            str(MODEL_PATHS[model_name]),
            "-f",
            str(seg),
            "-of",
            str(seg_txt_prefix),
            "-otxt",
            "-nt",
        ]

    def run(
        self,
        input_m4a: Path,
        model_name: str,
        segment_minutes: int,
        keep_intermediate: bool,
        progress_cb: Optional[ProgressCallback] = None,
    ) -> TranscriptionResult:
        """執行完整流程。"""
        job_dir = make_job_dir(self.output_root, input_m4a.name)
        log_file = self.log_root / f"{job_dir.name}.log"
        logger = setup_logger(log_file)

        def update(step: str, pct: int) -> None:
            logger.info("進度 %s%%：%s", pct, step)
            if progress_cb:
                progress_cb(step, pct)

        try:
            update("初始化工作目錄", 5)

            model_ok, model_msg = self.check_model_exists(model_name)
            if not model_ok:
                logger.error(model_msg)
                return TranscriptionResult(False, model_msg, log_file=log_file)

            whisper_bin = self.get_whisper_binary()
            if whisper_bin is None:
                candidates = "\n".join(str(path) for path in WHISPER_CANDIDATES)
                msg = (
                    "找不到可執行的 whisper.cpp 執行檔。\n"
                    "已檢查以下候選路徑（依優先順序）：\n"
                    f"{candidates}\n"
                    "請先確認 whisper-cli 已編譯並具有執行權限。"
                )
                logger.error(msg)
                return TranscriptionResult(False, msg, log_file=log_file)

            logger.info("使用 whisper 執行檔：%s", whisper_bin)

            # 1) m4a -> wav
            update("將 m4a 轉成 wav", 15)
            source_m4a = job_dir / input_m4a.name
            shutil.copy2(input_m4a, source_m4a)

            full_wav = job_dir / "full.wav"
            ok, msg = run_command(
                [
                    CONFIG.ffmpeg_binary,
                    "-y",
                    "-i",
                    str(source_m4a),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(full_wav),
                ],
                logger,
                "m4a 轉 wav",
            )
            if not ok:
                return TranscriptionResult(False, msg, log_file=log_file)

            # 2) 切段
            update("將 wav 依時間切段", 35)
            segments_dir = ensure_dir(job_dir / "segments")
            segment_seconds = max(60, segment_minutes * 60)
            segment_pattern = segments_dir / "segment_%03d.wav"
            ok, msg = run_command(
                [
                    CONFIG.ffmpeg_binary,
                    "-y",
                    "-i",
                    str(full_wav),
                    "-f",
                    "segment",
                    "-segment_time",
                    str(segment_seconds),
                    "-c",
                    "copy",
                    str(segment_pattern),
                ],
                logger,
                "wav 切段",
            )
            if not ok:
                return TranscriptionResult(False, msg, log_file=log_file)

            segment_files = sorted(segments_dir.glob("segment_*.wav"))
            if not segment_files:
                msg = "切段後找不到任何 segment_*.wav，流程中止。"
                logger.error(msg)
                return TranscriptionResult(False, msg, log_file=log_file)

            # 3) 每段轉寫
            update("逐段呼叫 whisper.cpp", 55)
            transcripts_dir = ensure_dir(job_dir / "transcripts")
            final_pieces: List[str] = []

            for idx, seg in enumerate(segment_files, start=1):
                seg_txt_prefix = transcripts_dir / seg.stem
                seg_progress = 55 + int((idx / len(segment_files)) * 35)
                update(f"轉寫第 {idx}/{len(segment_files)} 段：{seg.name}", seg_progress)

                cmd = self.build_whisper_command(whisper_bin, model_name, seg, seg_txt_prefix)
                ok, msg = run_command(
                    cmd,
                    logger,
                    f"whisper 轉寫 {seg.name}",
                    cwd=CONFIG.whisper_cpp_root,
                )
                if not ok:
                    return TranscriptionResult(False, msg, log_file=log_file)

                txt_file = seg_txt_prefix.with_suffix(".txt")
                if not txt_file.exists():
                    msg = f"轉寫完成但找不到輸出：{txt_file}"
                    logger.error(msg)
                    return TranscriptionResult(False, msg, log_file=log_file)

                text = txt_file.read_text(encoding="utf-8", errors="ignore").strip()
                final_pieces.append(f"===== {seg.name} =====\n{text}\n")

            # 4) 合併
            update("合併最終逐字稿", 95)
            final_txt = job_dir / "final_transcript.txt"
            final_txt.write_text("\n".join(final_pieces), encoding="utf-8")

            if not keep_intermediate:
                update("清理中間檔", 98)
                if full_wav.exists():
                    full_wav.unlink(missing_ok=True)
                if segments_dir.exists():
                    shutil.rmtree(segments_dir, ignore_errors=True)
                if transcripts_dir.exists():
                    shutil.rmtree(transcripts_dir, ignore_errors=True)

            update("完成", 100)
            return TranscriptionResult(True, "轉寫完成", final_txt_path=final_txt, log_file=log_file)

        except Exception as exc:  # noqa: BLE001 - 需要完整回報給 UI
            logger.exception("流程發生未預期錯誤：%s", exc)
            return TranscriptionResult(False, f"流程發生未預期錯誤：{exc}", log_file=log_file)


def model_status() -> Dict[str, bool]:
    """提供 UI 頁面載入時檢查模型狀態。"""
    return {name: path.exists() for name, path in MODEL_PATHS.items()}
