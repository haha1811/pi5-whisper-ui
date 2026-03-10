"""Streamlit 單頁式 UI。"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from config import CONFIG, LANGUAGE_OPTIONS, MODEL_PATHS
from transcriber import TranscriptionPipeline, model_status
from utils import ensure_dir, read_log_tail


MODEL_DESCRIPTIONS = {
    "small": "速度較快，資源較省",
    "medium": "速度與品質平衡",
    "large-v3-turbo": "品質較高，但在 Raspberry Pi 5 上執行時間較長、資源需求較高",
}


def main() -> None:
    st.set_page_config(page_title="Pi5 Whisper 逐字稿工具", page_icon="🎙️", layout="wide")
    st.title("🎙️ Raspberry Pi 5 本機逐字稿工具")
    st.caption("上傳 m4a 後，自動完成轉檔、切段、whisper.cpp 轉寫與合併。")

    ensure_dir(CONFIG.output_root)
    ensure_dir(CONFIG.log_root)

    st.subheader("模型檢查")
    status = model_status()
    for model_name in ["small", "medium", "large-v3-turbo"]:
        model_path = MODEL_PATHS[model_name]
        if status[model_name]:
            st.success(f"{model_name}: ✅ {model_path}")
        else:
            st.error(f"{model_name}: ❌ 缺少模型檔 {model_path}")

    st.divider()

    with st.form("transcribe_form"):
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

        threads = st.number_input(
            "執行緒數（threads）",
            min_value=1,
            max_value=32,
            value=CONFIG.default_threads,
            step=1,
        )

        st.info(f"模型：**{model_name}** - {MODEL_DESCRIPTIONS[model_name]}")
        st.info(f"目前語言設定：**{language}**；執行緒：**{int(threads)}**")

        keep_intermediate = st.checkbox("保留中間檔（wav、分段 wav、分段 txt）", value=False)
        output_root_input = st.text_input("輸出目錄", value=str(CONFIG.output_root))

        start = st.form_submit_button("開始轉寫", type="primary")

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

    upload_dir = ensure_dir(Path(output_root_input) / "_uploads")
    input_path = upload_dir / uploaded.name
    input_path.write_bytes(uploaded.getbuffer())

    progress_bar = st.progress(0)
    status_placeholder = st.empty()
    command_placeholder = st.empty()
    live_log_placeholder = st.empty()
    live_log_lines: list[str] = []

    def on_progress(step: str, pct: int) -> None:
        progress_bar.progress(max(0, min(100, pct)))
        status_placeholder.info(f"目前步驟：{step}（{pct}%）")
        if step.startswith("whisper-cli 指令："):
            command_placeholder.code(step.removeprefix("whisper-cli 指令："), language="bash")

    def on_log(line: str) -> None:
        live_log_lines.append(line)
        # 控制 UI 長度，僅保留最近 120 行
        display = "\n".join(live_log_lines[-120:])
        live_log_placeholder.code(display, language="log")

    result = pipeline.run(
        input_m4a=input_path,
        model_name=model_name,
        language=language,
        threads=int(threads),
        segment_minutes=int(segment_minutes),
        keep_intermediate=keep_intermediate,
        progress_cb=on_progress,
        log_cb=on_log,
    )

    if result.log_file:
        st.subheader("執行 Log（檔案尾端）")
        st.code(read_log_tail(result.log_file), language="log")

    if not result.success:
        st.error(result.message)
        return

    st.success(result.message)

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
