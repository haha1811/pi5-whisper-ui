"""逐字稿流程核心。"""

from __future__ import annotations

import os
import shutil
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from config import CONFIG, LANGUAGE_OPTIONS, MODEL_PATHS, WHISPER_CANDIDATES
from utils import ensure_dir, make_job_dir, run_command, setup_logger

ProgressCallback = Callable[[str, int], None]
LogCallback = Callable[[str], None]


@dataclass
class TranscriptionResult:
    success: bool
    message: str
    final_txt_path: Optional[Path] = None
    log_file: Optional[Path] = None
    output_directory: Optional[Path] = None
    audio_duration_seconds: float = 0.0


class TranscriptionPipeline:
    """封裝整個轉寫流程。"""

    def __init__(self, output_root: Path | None = None, log_root: Path | None = None) -> None:
        self.output_root = ensure_dir(output_root or CONFIG.output_root)
        self.log_root = ensure_dir(log_root or CONFIG.log_root)

    @staticmethod
    def get_whisper_binary() -> Optional[Path]:
        for candidate in WHISPER_CANDIDATES:
            if candidate.exists() and candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        return None

    @staticmethod
    def check_model_exists(model_name: str) -> tuple[bool, str]:
        model_path = MODEL_PATHS.get(model_name)
        if model_path is None:
            return False, f"未知模型：{model_name}"
        if not model_path.exists():
            return False, f"模型不存在：{model_path}"
        return True, f"模型可用：{model_path}"

    @staticmethod
    def check_language(language: str) -> tuple[bool, str]:
        if language not in LANGUAGE_OPTIONS:
            return False, f"不支援的語言：{language}"
        return True, f"語言設定：{language}"

    @staticmethod
    def get_wav_duration_seconds(wav_path: Path) -> float:
        with wave.open(str(wav_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            if rate <= 0:
                return 0.0
            return frames / float(rate)

    @staticmethod
    def build_whisper_command(
        whisper_bin: Path,
        model_name: str,
        seg: Path,
        seg_txt_prefix: Path,
        language: str,
        threads: int,
    ) -> List[str]:
        cmd: List[str] = [
            str(whisper_bin),
            "-m",
            str(MODEL_PATHS[model_name]),
            "-f",
            str(seg),
            "-of",
            str(seg_txt_prefix),
            "-otxt",
            "-nt",
            "-t",
            str(max(1, threads)),
        ]
        if language != "auto":
            cmd.extend(["-l", language])
        return cmd

    def run(
        self,
        input_m4a: Path,
        model_name: str,
        language: str,
        threads: int,
        segment_minutes: int,
        keep_intermediate: bool,
        progress_cb: Optional[ProgressCallback] = None,
        log_cb: Optional[LogCallback] = None,
    ) -> TranscriptionResult:
        job_dir = make_job_dir(self.output_root, input_m4a.name)
        log_file = self.log_root / f"{job_dir.name}.log"
        logger = setup_logger(log_file)
        audio_duration_seconds = 0.0

        def update(step: str, pct: int) -> None:
            logger.info("進度 %s%%：%s", pct, step)
            if progress_cb:
                progress_cb(step, pct)

        try:
            update("初始化工作目錄", 5)

            model_ok, model_msg = self.check_model_exists(model_name)
            if not model_ok:
                logger.error(model_msg)
                return TranscriptionResult(False, model_msg, log_file=log_file, output_directory=job_dir)

            lang_ok, lang_msg = self.check_language(language)
            if not lang_ok:
                logger.error(lang_msg)
                return TranscriptionResult(False, lang_msg, log_file=log_file, output_directory=job_dir)

            whisper_bin = self.get_whisper_binary()
            if whisper_bin is None:
                candidates = "\n".join(str(path) for path in WHISPER_CANDIDATES)
                msg = "找不到可執行的 whisper.cpp 執行檔。\n已檢查以下候選路徑（依優先順序）：\n" + candidates
                logger.error(msg)
                return TranscriptionResult(False, msg, log_file=log_file, output_directory=job_dir)

            logger.info("使用語言：%s", language)
            logger.info("使用執行緒：%s", max(1, threads))
            logger.info("使用 whisper 執行檔：%s", whisper_bin)

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
                on_output=log_cb,
            )
            if not ok:
                return TranscriptionResult(False, msg, log_file=log_file, output_directory=job_dir)

            audio_duration_seconds = self.get_wav_duration_seconds(full_wav)
            logger.info("音檔長度（秒）：%.2f", audio_duration_seconds)

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
                on_output=log_cb,
            )
            if not ok:
                return TranscriptionResult(False, msg, log_file=log_file, output_directory=job_dir)

            segment_files = sorted(segments_dir.glob("segment_*.wav"))
            if not segment_files:
                msg = "切段後找不到任何 segment_*.wav，流程中止。"
                logger.error(msg)
                return TranscriptionResult(False, msg, log_file=log_file, output_directory=job_dir)

            update("逐段呼叫 whisper.cpp", 55)
            transcripts_dir = ensure_dir(job_dir / "transcripts")
            final_pieces: List[str] = []

            for idx, seg in enumerate(segment_files, start=1):
                seg_txt_prefix = transcripts_dir / seg.stem
                seg_progress = 55 + int((idx / len(segment_files)) * 35)
                cmd = self.build_whisper_command(whisper_bin, model_name, seg, seg_txt_prefix, language, threads)
                update(f"Segment {idx} / {len(segment_files)}", seg_progress)
                update(f"whisper-cli 指令：{' '.join(cmd)}", seg_progress)

                ok, msg = run_command(
                    cmd,
                    logger,
                    f"whisper 轉寫 {seg.name}",
                    cwd=CONFIG.whisper_cpp_root,
                    on_output=log_cb,
                )
                if not ok:
                    return TranscriptionResult(False, msg, log_file=log_file, output_directory=job_dir)

                txt_file = seg_txt_prefix.with_suffix(".txt")
                if not txt_file.exists():
                    msg = f"轉寫完成但找不到輸出：{txt_file}"
                    logger.error(msg)
                    return TranscriptionResult(False, msg, log_file=log_file, output_directory=job_dir)

                text = txt_file.read_text(encoding="utf-8", errors="ignore").strip()
                final_pieces.append(f"===== {seg.name} =====\n{text}\n")

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
            return TranscriptionResult(
                True,
                "轉寫完成",
                final_txt_path=final_txt,
                log_file=log_file,
                output_directory=job_dir,
                audio_duration_seconds=audio_duration_seconds,
            )

        except Exception as exc:  # noqa: BLE001
            logger.exception("流程發生未預期錯誤：%s", exc)
            return TranscriptionResult(
                False,
                f"流程發生未預期錯誤：{exc}",
                log_file=log_file,
                output_directory=job_dir,
                audio_duration_seconds=audio_duration_seconds,
            )


def model_status() -> Dict[str, bool]:
    return {name: path.exists() for name, path in MODEL_PATHS.items()}
