"""Streamlit 單頁式 UI。

提供上傳、參數設定、流程執行、進度與結果下載。
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from config import CONFIG, MODEL_PATHS
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

    # 頁面載入時先做模型檢查
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

        col1, col2 = st.columns(2)
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
                help="small：速度較快，資源較省\n\nmedium：速度與品質平衡\n\nlarge-v3-turbo：品質較高，但 Pi5 執行較慢",
            )

        st.info(f"模型說明：**{model_name}** - {MODEL_DESCRIPTIONS[model_name]}")

        keep_intermediate = st.checkbox("保留中間檔（wav、分段 wav、分段 txt）", value=False)
        output_root_input = st.text_input("輸出目錄", value=str(CONFIG.output_root))

        start = st.form_submit_button("開始轉寫", type="primary")

    if not start:
        return

    if uploaded is None:
        st.error("請先上傳 .m4a 檔案。")
        return

    # 執行前再次檢查模型
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

    def on_progress(step: str, pct: int) -> None:
        progress_bar.progress(max(0, min(100, pct)))
        status_placeholder.info(f"目前步驟：{step}（{pct}%）")

    result = pipeline.run(
        input_m4a=input_path,
        model_name=model_name,
        segment_minutes=int(segment_minutes),
        keep_intermediate=keep_intermediate,
        progress_cb=on_progress,
    )

    if result.log_file:
        st.subheader("執行 Log")
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
