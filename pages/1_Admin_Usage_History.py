"""Admin / Usage History 頁面。"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from config import CONFIG
from history import HistoryStore
from utils import format_bytes, format_seconds, get_dir_size_bytes


st.set_page_config(page_title="Admin / Usage History", page_icon="🛠️", layout="wide")
st.title("🛠️ Admin / Usage History")

store = HistoryStore()
records = store.list_records()

jobs_count = len(records)
disk_usage = get_dir_size_bytes(CONFIG.output_root)

col_a, col_b = st.columns(2)
col_a.metric("Total Jobs", jobs_count)
col_b.metric("Output Disk Usage", format_bytes(disk_usage))

st.divider()
st.subheader("History Table")

if not records:
    st.info("尚無使用紀錄。")
else:
    table_rows = [
        {
            "id": r.id,
            "timestamp": r.timestamp,
            "filename": r.filename,
            "model": r.model,
            "language": r.language,
            "threads": r.threads,
            "processing_time": format_seconds(r.processing_time),
            "output_path": r.output_directory,
        }
        for r in records
    ]
    st.dataframe(table_rows, use_container_width=True)

st.divider()
st.subheader("Delete / Cleanup Tools")

if records:
    selected_id = st.selectbox("選擇要管理的紀錄 ID", options=[r.id for r in records])
    selected_record = next((r for r in records if r.id == selected_id), None)

    if selected_record:
        st.caption(f"已選擇：{selected_record.filename} ({selected_record.timestamp})")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Delete record"):
            store.delete_record(selected_id)
            st.success(f"已刪除紀錄 ID {selected_id}")
            st.rerun()
    with col2:
        if st.button("Delete associated output directory"):
            if selected_record:
                output_dir = Path(selected_record.output_directory)
                if output_dir.exists():
                    store.delete_record_and_output(selected_id)
                    st.success(f"已刪除紀錄與輸出資料夾：{output_dir}")
                else:
                    store.delete_record(selected_id)
                    st.warning("輸出資料夾不存在，僅刪除紀錄。")
                st.rerun()

cleanup_days = st.number_input("刪除幾天前的工作", min_value=1, max_value=3650, value=30, step=1)
delete_outputs = st.checkbox("同時刪除對應輸出資料夾", value=True)
if st.button("Delete jobs older than X days"):
    deleted = store.cleanup_older_than_days(int(cleanup_days), delete_outputs=delete_outputs)
    st.success(f"完成清理，共刪除 {deleted} 筆紀錄")
    st.rerun()
