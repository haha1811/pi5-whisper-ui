"""Streamlit 主頁：轉寫執行。"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict

import streamlit as st

from config import CONFIG, LANGUAGE_OPTIONS, MODEL_PATHS
from history import HistoryStore
from job_state import JobStateStore
from monitor import get_cpu_logical_cores, get_system_usage_with_timestamp
from transcriber import TranscriptionPipeline, model_status
from utils import ensure_dir, format_seconds, read_log_tail

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # noqa: BLE001
    st_autorefresh = None

MODEL_DESCRIPTIONS = {
    "small": "速度較快，資源較省",
    "medium": "速度與品質平衡",
    "large-v3-turbo": "品質較高，但在 Raspberry Pi 5 上執行時間較長、資源需求較高",
}
UI_REFRESH_SECONDS = 2


def parse_segment(step: str) -> str:
    return step if step.startswith("Segment ") else ""


def try_recover_final_transcript(output_path: Path) -> Path | None:
    """若 transcripts 已存在但 final_transcript 缺失，嘗試補做 merge。"""
    transcripts_dir = output_path / "transcripts"
    final_txt = output_path / "final_transcript.txt"
    if final_txt.exists():
        return final_txt
    if not transcripts_dir.exists():
        return None

    txt_files = sorted(transcripts_dir.glob("segment_*.txt"))
    if not txt_files:
        return None

    pieces: list[str] = []
    for txt in txt_files:
        content = txt.read_text(encoding="utf-8", errors="ignore").strip()
        pieces.append(f"===== {txt.stem}.wav =====\n{content}\n")

    final_txt.write_text("\n".join(pieces), encoding="utf-8")
    return final_txt


def load_ui_styles() -> None:
    """Load minimal custom UI styles with silent fallback."""
    css_path = Path(__file__).resolve().parent / "assets" / "style.css"
    try:
        if css_path.exists():
            st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    except Exception:  # noqa: BLE001
        # Silent fallback by design.
        pass


def get_status_badge_html(status: str | None) -> str:
    """Return status badge HTML with unknown fallback and safe text escaping."""
    status_value = (status or "unknown").strip().lower() or "unknown"
    badge_map = {
        "running": ("Running", "running"),
        "completed": ("Completed", "completed"),
        "failed": ("Failed", "failed"),
        "interrupted": ("Interrupted", "interrupted"),
        "idle": ("Idle", "idle"),
    }
    label, css_suffix = badge_map.get(status_value, (status_value.title(), "unknown"))
    return f"<span class='status-badge status-{css_suffix}'>{escape(label)}</span>"


def pick_main_state(disk_state: Dict[str, Any] | None) -> tuple[Dict[str, Any] | None, str]:
    """首頁主狀態選擇規則：running 優先，否則 latest。"""
    state = st.session_state.get("current_job_state")

    # 磁碟有更新就覆蓋 session，確保切頁回來是最新。
    if disk_state:
        if (not state) or (disk_state.get("last_updated", "") >= state.get("last_updated", "")):
            state = disk_state
            st.session_state.current_job_state = state

    if not state:
        return None, "none"

    if state.get("status") == "running":
        return state, "active"

    return state, "latest"


def render_job_state(state: Dict[str, Any], state_store: JobStateStore, state_kind: str) -> None:
    """顯示目前任務狀態。"""
    status = state.get("status", "idle")
    job_id = state.get("job_id", "-")
    start_time = state.get("start_time", "-")
    last_updated = state.get("last_updated", "-")
    current_pid = int(state.get("current_pid") or 0)

    with st.container(border=True):
        if state_kind == "active":
            st.markdown("### Current Active Job")
        else:
            st.markdown("### Latest Job")
        st.markdown(get_status_badge_html(status), unsafe_allow_html=True)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Job ID", job_id)
        m2.metric("Current PID", str(current_pid if current_pid > 0 else "-"))
        m3.metric("Start time", start_time)
        m4.metric("Last updated", last_updated)
        st.caption(f"UI refreshed at: {datetime.now().strftime('%H:%M:%S')}")

    progress = int(state.get("progress_percent", 0))
    current_step = state.get("current_step", "尚未開始")
    current_segment = state.get("current_segment", "")

    st.progress(max(0, min(100, progress)))
    st.info(f"目前步驟：{current_step} ({progress}%)")
    if current_segment:
        st.caption(f"目前 segment：{current_segment}")

    log_path = state.get("log_path")
    if log_path:
        st.subheader("目前 Log（每次自動刷新重讀最後幾行）")
        st.code(read_log_tail(Path(log_path)), language="log")

    output_path = state.get("output_path")
    if output_path:
        op = Path(output_path)
        final_txt = op / "final_transcript.txt"
        if not final_txt.exists() and (op / "transcripts").exists():
            st.warning("偵測到 transcripts 已存在但 final_transcript 缺失。")
            if st.button("嘗試恢復此任務（補產生 final transcript）", key=f"recover_{job_id}"):
                recovered = try_recover_final_transcript(op)
                if recovered and recovered.exists():
                    state["final_txt_path"] = str(recovered)
                    state["status"] = "completed"
                    state["message"] = "已自動恢復並補產生 final transcript。"
                    state["last_updated"] = datetime.now().isoformat(timespec="seconds")
                    state_store.save(state)
                    st.session_state.current_job_state = state
                    st.success("恢復成功，已產生 final_transcript.txt")
                    st.rerun()
                else:
                    st.error("恢復失敗，找不到可合併的 segment txt。")

    if status == "completed":
        with st.container(border=True):
            st.success(state.get("message", "最近一次任務已完成。"))
            final_txt_path = state.get("final_txt_path")
            if final_txt_path and Path(final_txt_path).exists():
                text = Path(final_txt_path).read_text(encoding="utf-8", errors="ignore")
                st.subheader("最終逐字稿預覽")
                st.text_area("內容", value=text, height=300)
                st.download_button(
                    label="下載最終逐字稿 TXT",
                    data=text.encode("utf-8"),
                    file_name=Path(final_txt_path).name,
                    mime="text/plain",
                )
    elif status == "failed":
        st.error(state.get("message", "任務失敗"))
    elif status == "interrupted":
        st.warning(state.get("message", "任務疑似中斷"))


def main() -> None:
    st.set_page_config(page_title="Pi5 Whisper 逐字稿工具", page_icon="🎙️", layout="wide")
    load_ui_styles()
    if st_autorefresh is not None:
        st_autorefresh(interval=UI_REFRESH_SECONDS * 1000, key="ui_autorefresh_2s")

    st.title("🎙️ Raspberry Pi 5 本機逐字稿工具")
    st.caption("上傳 m4a 後，自動完成轉檔、切段、whisper.cpp 轉寫與合併。")

    ensure_dir(CONFIG.output_root)
    ensure_dir(CONFIG.log_root)
    ensure_dir(CONFIG.data_root)

    state_store = JobStateStore(CONFIG.current_job_state_path)
    disk_state = state_store.mark_interrupted_if_stale(CONFIG.stale_running_job_seconds)
    main_state, state_kind = pick_main_state(disk_state)

    cpu_cores = get_cpu_logical_cores()
    st.sidebar.markdown("### System")
    st.sidebar.metric("CPU Logical Cores", cpu_cores)
    st.sidebar.metric("Recommended Threads", cpu_cores)
    usage = get_system_usage_with_timestamp()
    if usage:
        cpu, mem, ts = usage
        st.sidebar.metric("CPU Usage", f"{cpu:.1f}%")
        st.sidebar.metric("Memory Usage", f"{mem:.1f}%")
        st.sidebar.caption(f"Last updated: {ts}")
    else:
        st.sidebar.info("psutil 未安裝，略過 CPU/Memory 監控。")

    header_left, header_right = st.columns([2, 1])
    with header_left:
        if main_state and main_state.get("status") == "running":
            st.info("目前有任務正在執行中，可切換頁面後再返回查看，任務不會中斷。")
    with header_right:
        state_label = main_state.get("status") if main_state else "idle"
        st.markdown("#### 系統狀態")
        st.markdown(get_status_badge_html(state_label), unsafe_allow_html=True)

    with st.container(border=True):
        st.subheader("模型檢查")
        status = model_status()
        for model_name in ["small", "medium", "large-v3-turbo"]:
            model_path = MODEL_PATHS[model_name]
            if status[model_name]:
                st.success(f"{model_name}: ✅ {model_path}")
            else:
                st.error(f"{model_name}: ❌ 缺少模型檔 {model_path}")

    form_col, state_col = st.columns([2, 1])
    with form_col:
        with st.container(border=True):
            uploaded = st.file_uploader("上傳 m4a 錄音檔", type=["m4a"])
            col1, col2, col3 = st.columns(3)
            with col1:
                segment_minutes = st.number_input("分段長度（分鐘）", min_value=1, max_value=120, value=CONFIG.default_segment_minutes, step=1)
            with col2:
                model_name = st.selectbox("選擇模型", options=["small", "medium", "large-v3-turbo"], index=["small", "medium", "large-v3-turbo"].index(CONFIG.default_model_name))
            with col3:
                language = st.selectbox("辨識語言", options=LANGUAGE_OPTIONS, index=LANGUAGE_OPTIONS.index(CONFIG.default_language))

            threads = st.number_input("執行緒數（threads）", min_value=1, max_value=cpu_cores, value=min(CONFIG.default_threads, cpu_cores), step=1)
            threads_used = max(1, min(int(threads), cpu_cores))
            st.code("\n".join([f"Model: {model_name}", f"Language: {language}", f"Threads: {threads_used}/{cpu_cores}", f"Segment: {int(segment_minutes)} min"]), language="text")

            keep_intermediate = st.checkbox("保留中間檔（wav、分段 wav、分段 txt）", value=False)
            output_root_input = st.text_input("輸出目錄", value=str(CONFIG.output_root))

            disable_start = bool(main_state and main_state.get("status") == "running")
            if disable_start:
                st.warning("目前已有任務執行中，請等待完成後再啟動新任務。")
            start = st.button("開始轉寫", type="primary", disabled=disable_start)

    with state_col:
        with st.container(border=True):
            st.markdown("#### 執行摘要")
            st.markdown(get_status_badge_html(main_state.get("status") if main_state else "idle"), unsafe_allow_html=True)
            if main_state:
                st.caption(f"Job ID: {main_state.get('job_id', '-')}")
                st.caption(f"Step: {main_state.get('current_step', '尚未開始')}")
            else:
                st.caption("目前無任務")

    # 只有未按開始時才顯示舊任務主區塊，避免舊/新同屏混淆
    if not start:
        if main_state:
            render_job_state(main_state, state_store, state_kind)
        else:
            st.info("目前無執行中的任務。")
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

    job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    running_state: Dict[str, Any] = {
        "job_id": job_id,
        "status": "running",
        "progress_percent": 0,
        "current_step": "初始化中",
        "current_segment": "",
        "current_pid": 0,
        "heartbeat_source": "init",
        "log_path": "",
        "output_path": "",
        "final_txt_path": "",
        "start_time": datetime.now().isoformat(timespec="seconds"),
        "end_time": "",
        "last_updated": datetime.now().isoformat(timespec="seconds"),
        "message": "",
    }
    st.session_state.current_job_state = running_state
    state_store.save(running_state)

    # 新任務啟動後，僅顯示新任務資訊
    st.markdown("### Current Active Job")
    st.markdown(get_status_badge_html("running"), unsafe_allow_html=True)
    st.caption(f"Job ID: {job_id}")

    progress_bar = st.progress(0)
    status_placeholder = st.empty()
    command_placeholder = st.empty()
    live_log_placeholder = st.empty()
    live_log_lines: list[str] = []

    def update_state(**kwargs: Any) -> None:
        state = dict(st.session_state.current_job_state)
        state.update(kwargs)
        state["last_updated"] = datetime.now().isoformat(timespec="seconds")
        st.session_state.current_job_state = state
        state_store.save(state)

    def on_progress(step: str, pct: int) -> None:
        progress_bar.progress(max(0, min(100, pct)))
        status_placeholder.info(f"Processing... {step} ({pct}%)")
        if step.startswith("whisper-cli 指令："):
            command_placeholder.code(step.removeprefix("whisper-cli 指令："), language="bash")
        update_state(progress_percent=int(max(0, min(100, pct))), current_step=step, current_segment=parse_segment(step), heartbeat_source="progress")

    def on_log(line: str) -> None:
        live_log_lines.append(line)
        live_log_placeholder.code("\n".join(live_log_lines[-120:]), language="log")
        update_state(heartbeat_source="log")

    def on_heartbeat(step_name: str, pid: int) -> None:
        update_state(
            current_step=step_name,
            current_pid=(pid if pid > 0 else st.session_state.current_job_state.get("current_pid", 0)),
            heartbeat_source=("process_start" if pid > 0 else "heartbeat"),
        )

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
        heartbeat_cb=on_heartbeat,
    )
    processing_time_seconds = time.perf_counter() - start_perf

    if result.log_file:
        st.subheader("執行 Log（檔案尾端）")
        st.code(read_log_tail(result.log_file), language="log")

    if not result.success:
        update_state(
            status="failed",
            end_time=datetime.now().isoformat(timespec="seconds"),
            current_pid=0,
            message=result.message,
            log_path=str(result.log_file) if result.log_file else "",
            output_path=str(result.output_directory) if result.output_directory else "",
        )
        st.error(result.message)
        return

    audio_duration_seconds = result.audio_duration_seconds
    rtf = (processing_time_seconds / audio_duration_seconds) if audio_duration_seconds > 0 else 0.0

    history = HistoryStore()
    if result.output_directory:
        try:
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
        except Exception as exc:  # noqa: BLE001
            st.warning(f"使用紀錄寫入失敗：{exc}")

    update_state(
        status="completed",
        progress_percent=100,
        current_step="完成",
        current_pid=0,
        end_time=datetime.now().isoformat(timespec="seconds"),
        log_path=str(result.log_file) if result.log_file else "",
        output_path=str(result.output_directory) if result.output_directory else "",
        final_txt_path=str(result.final_txt_path) if result.final_txt_path else "",
        message="轉寫完成",
        heartbeat_source="complete",
    )

    st.success("轉錄完成")
    m1, m2, m3 = st.columns(3)
    m1.metric("音檔長度", format_seconds(audio_duration_seconds))
    m2.metric("處理時間", format_seconds(processing_time_seconds))
    m3.metric("RTF", f"{rtf:.2f}x")

    if result.final_txt_path and result.final_txt_path.exists():
        with st.container(border=True):
            text = result.final_txt_path.read_text(encoding="utf-8", errors="ignore")
            st.subheader("最終逐字稿預覽")
            st.text_area("內容", value=text, height=400)
            st.download_button("下載最終逐字稿 TXT", text.encode("utf-8"), file_name=result.final_txt_path.name, mime="text/plain")


if __name__ == "__main__":
    main()
