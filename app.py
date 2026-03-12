"""Streamlit 主頁：轉寫執行。"""

from __future__ import annotations

import time
from pathlib import Path

import streamlit as st

from config import CONFIG, LANGUAGE_OPTIONS, MODEL_PATHS
from history import HistoryStore
from monitor import get_cpu_logical_cores, get_system_usage_with_timestamp
from transcriber import TranscriptionPipeline, model_status
from utils import ensure_dir, format_seconds, read_log_tail

try:
    # 可選套件：讓頁面每 60 秒自動 rerun，更新 sidebar 監控數值。
    from streamlit_autorefresh import st_autorefresh
except Exception:  # noqa: BLE001
    st_autorefresh = None


MODEL_DESCRIPTIONS = {
    "small": "速度較快，資源較省",
    "medium": "速度與品質平衡",
    "large-v3-turbo": "品質較高，但在 Raspberry Pi 5 上執行時間較長、資源需求較高",
}

MONITOR_REFRESH_SECONDS = 60


def main() -> None:
    st.set_page_config(page_title="Pi5 Whisper 逐字稿工具", page_icon="🎙️", layout="wide")
    st.title("🎙️ Raspberry Pi 5 本機逐字稿工具")
    st.caption("上傳 m4a 後，自動完成轉檔、切段、whisper.cpp 轉寫與合併。")

    ensure_dir(CONFIG.output_root)
    ensure_dir(CONFIG.log_root)
    ensure_dir(CONFIG.data_root)

    # 若有可用套件，使用輕量自動刷新（60 秒）更新監控資訊。
    # Streamlit 在長任務期間不會中斷執行，重繪會在安全時機發生。
    if st_autorefresh is not None:
        st_autorefresh(interval=MONITOR_REFRESH_SECONDS * 1000, key="system_monitor_autorefresh")

    cpu_cores = get_cpu_logical_cores()
    recommended_threads = cpu_cores

    # sidebar 監控區塊：使用 placeholders，避免整個頁面大幅閃動。
    st.sidebar.markdown("### System")
    cores_placeholder = st.sidebar.empty()
    reco_placeholder = st.sidebar.empty()
    cpu_placeholder = st.sidebar.empty()
    mem_placeholder = st.sidebar.empty()
    updated_placeholder = st.sidebar.empty()

    cores_placeholder.metric("CPU Logical Cores", cpu_cores)
    reco_placeholder.metric("Recommended Threads", recommended_threads)

    if "last_monitor_refresh_at" not in st.session_state:
        st.session_state.last_monitor_refresh_at = 0.0

    def refresh_monitor(force: bool = False) -> None:
        """刷新 sidebar 監控數值。

        - force=True：強制更新（例如初始化）
        - force=False：最多每 60 秒更新一次（避免頻繁重繪）
        """
        now = time.time()
        last = float(st.session_state.get("last_monitor_refresh_at", 0.0))
        if (not force) and (now - last < MONITOR_REFRESH_SECONDS):
            return

        usage = get_system_usage_with_timestamp()
        if usage:
            cpu, mem, ts = usage
            cpu_placeholder.metric("CPU Usage", f"{cpu:.1f}%")
            mem_placeholder.metric("Memory Usage", f"{mem:.1f}%")
            updated_placeholder.caption(f"Last updated: {ts}")
        else:
            cpu_placeholder.info("psutil 未安裝，略過 CPU/Memory 監控。")
            mem_placeholder.empty()
            updated_placeholder.empty()

        st.session_state.last_monitor_refresh_at = now

    if CONFIG.enable_system_monitor:
        refresh_monitor(force=True)

    st.subheader("模型檢查")
    status = model_status()
    for model_name in ["small", "medium", "large-v3-turbo"]:
        model_path = MODEL_PATHS[model_name]
        if status[model_name]:
            st.success(f"{model_name}: ✅ {model_path}")
        else:
            st.error(f"{model_name}: ❌ 缺少模型檔 {model_path}")

    st.divider()

    uploaded = st.file_uploader("上傳 m4a 錄音檔", type=["m4a"])

    col1, col2, col3 = st.columns(3)
    with col1:
        segment_minutes = st.number_input(
            "分段長度（分鐘）",
            min_value=1,
            max_value=120,
            value=CONFIG.default_segment_minutes,
            step=1,
        )
    with col2:
        model_name = st.selectbox(
            "選擇模型",
            options=["small", "medium", "large-v3-turbo"],
            index=["small", "medium", "large-v3-turbo"].index(CONFIG.default_model_name),
        )
    with col3:
        language = st.selectbox(
            "辨識語言",
            options=LANGUAGE_OPTIONS,
            index=LANGUAGE_OPTIONS.index(CONFIG.default_language),
            help="auto=自動判斷；zh=中文；en=英文；ja=日文",
        )

    st.markdown("#### 執行緒設定")
    st.caption("執行緒數（threads）建議值：與 CPU 核心數相同；設太高不一定更快，可能增加系統負擔。")
    st.info(f"目前裝置偵測到 **{cpu_cores}** 個邏輯核心，建議 threads 設為 **{recommended_threads}**。")

    threads = st.number_input(
        "執行緒數（threads）",
        min_value=1,
        max_value=cpu_cores,
        value=min(CONFIG.default_threads, cpu_cores),
        step=1,
        help="系統已限制最大值為 CPU 邏輯核心數，避免不合理設定造成效能下降。",
    )

    threads_used = max(1, min(int(threads), cpu_cores))
    if threads_used != int(threads):
        st.warning(f"threads 已自動修正為 {threads_used}（CPU 邏輯核心上限：{cpu_cores}）。")

    st.subheader("Current Settings")
    st.code(
        "\n".join(
            [
                f"Model: {model_name}",
                f"Language: {language}",
                f"Threads: {threads_used} / CPU Logical Cores: {cpu_cores}",
                f"Segment length: {int(segment_minutes)} minutes",
            ]
        ),
        language="text",
    )
    st.info(f"模型：**{model_name}** - {MODEL_DESCRIPTIONS[model_name]}")

    keep_intermediate = st.checkbox("保留中間檔（wav、分段 wav、分段 txt）", value=False)
    output_root_input = st.text_input("輸出目錄", value=str(CONFIG.output_root))
    start = st.button("開始轉寫", type="primary")

    if not start:
        return

    if uploaded is None:
        st.error("請先上傳 .m4a 檔案。")
        return

    pipeline = TranscriptionPipeline(output_root=Path(output_root_input), log_root=CONFIG.log_root)
    ok, msg = pipeline.check_model_exists(model_name)
    if not ok:
        st.error(msg)
        return

    safe_name = Path(uploaded.name).name
    upload_dir = ensure_dir(Path(output_root_input) / "_uploads")
    input_path = upload_dir / safe_name
    input_path.write_bytes(uploaded.getbuffer())

    progress_bar = st.progress(0)
    status_placeholder = st.empty()
    command_placeholder = st.empty()
    live_log_placeholder = st.empty()
    live_log_lines: list[str] = []

    def on_progress(step: str, pct: int) -> None:
        progress_bar.progress(max(0, min(100, pct)))
        status_placeholder.info(f"Processing... {step} ({pct}%)")
        if step.startswith("whisper-cli 指令："):
            command_placeholder.code(step.removeprefix("whisper-cli 指令："), language="bash")

    def on_log(line: str) -> None:
        live_log_lines.append(line)
        live_log_placeholder.code("\n".join(live_log_lines[-120:]), language="log")
        # 轉寫期間也嘗試按節流規則更新 sidebar 監控。
        if CONFIG.enable_system_monitor:
            refresh_monitor(force=False)

    start_perf = time.perf_counter()
    result = pipeline.run(
        input_m4a=input_path,
        model_name=model_name,
        language=language,
        threads=threads_used,
        segment_minutes=int(segment_minutes),
        keep_intermediate=keep_intermediate,
        progress_cb=on_progress,
        log_cb=on_log,
    )
    processing_time_seconds = time.perf_counter() - start_perf

    if result.log_file:
        st.subheader("執行 Log（檔案尾端）")
        st.code(read_log_tail(result.log_file), language="log")

    if not result.success:
        st.error(result.message)
        return

    audio_duration_seconds = result.audio_duration_seconds
    rtf = (processing_time_seconds / audio_duration_seconds) if audio_duration_seconds > 0 else 0.0

    history = HistoryStore()
    if result.output_directory:
        history.add_record(
            filename=safe_name,
            audio_duration_seconds=audio_duration_seconds,
            model=model_name,
            language=language,
            threads_used=threads_used,
            processing_time_seconds=processing_time_seconds,
            rtf=rtf,
            cpu_logical_cores=cpu_cores,
            output_directory=result.output_directory,
        )

    st.success("轉錄完成")

    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("音檔長度", format_seconds(audio_duration_seconds))
    metric2.metric("處理時間", format_seconds(processing_time_seconds))
    metric3.metric("RTF", f"{rtf:.2f}x")

    if rtf < 1:
        st.info("RTF < 1：轉錄速度比即時播放更快。")
    elif rtf > 1:
        st.warning("RTF > 1：轉錄速度比即時播放慢。")
    else:
        st.info("RTF = 1：轉錄速度約等於即時播放。")

    st.markdown(
        "\n".join(
            [
                f"Audio length: {format_seconds(audio_duration_seconds)}  ",
                f"Processing time: {format_seconds(processing_time_seconds)}  ",
                f"RTF: {rtf:.2f}x  ",
                f"Model used: {model_name}  ",
                f"Language: {language}  ",
                f"Threads: {threads_used} / CPU Logical Cores: {cpu_cores}",
            ]
        )
    )

    if result.final_txt_path and result.final_txt_path.exists():
        text = result.final_txt_path.read_text(encoding="utf-8", errors="ignore")
        st.subheader("最終逐字稿預覽")
        st.text_area("內容", value=text, height=400)
        st.download_button(
            label="下載最終逐字稿 TXT",
            data=text.encode("utf-8"),
            file_name=result.final_txt_path.name,
            mime="text/plain",
        )


if __name__ == "__main__":
    main()
