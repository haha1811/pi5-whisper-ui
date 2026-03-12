# pi5-whisper-ui

在 Raspberry Pi 5 上執行的本機 Streamlit Web UI：把手機錄音檔 `.m4a` 自動轉成逐字稿 `.txt`。

## 專案目錄結構

```text
pi5-whisper-ui/
├─ app.py
├─ transcriber.py
├─ utils.py
├─ history.py                  # 使用紀錄 SQLite
├─ monitor.py                  # CPU / Memory 監控
├─ config.py
├─ pages/
│  └─ 1_Admin_Usage_History.py # Admin / Usage History 頁面
├─ deploy/systemd/pi5-whisper-ui.service
├─ scripts/install-service.sh
├─ requirements.txt
└─ README.md
```

## 功能

- 上傳 `.m4a` 檔
- 設定切段長度（預設 15 分鐘）
- 選擇模型（small / medium / large-v3-turbo）
- 選擇辨識語言（auto / zh / en / ja，預設 zh）
- 可設定 whisper 執行緒數（threads）
- 動態顯示 Current Settings（選項一改就更新）
- 顯示目前 step、segment 進度與即時 log
- 完成後顯示音檔長度、模型、語言、threads、處理時間
- 下載最終 `.txt`
- Admin 頁面可查看歷史、刪除紀錄、刪除輸出資料夾、批次清理舊任務

## 使用紀錄（Usage History）

- 資料庫：`/mnt/ssd/workspace/pi5-whisper-ui/data/history.db`
- 每次成功轉寫會記錄：
  - timestamp
  - filename
  - audio_duration
  - model
  - language
  - threads
  - processing_time
  - output_directory

## Admin 面板

在 Streamlit 側欄切換到 `Admin / Usage History` 頁面，可執行：

- 查看使用紀錄表格
- Delete record（只刪除 DB 紀錄）
- Delete associated output directory（刪除 DB + 輸出資料夾）
- Delete jobs older than X days（批次清理）
- 查看 Total Jobs 與 outputs 磁碟用量

## 安裝

```bash
cd /mnt/ssd/workspace/pi5-whisper-ui
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 啟動

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

## systemd 開機自動啟動

```bash
cd /mnt/ssd/workspace/pi5-whisper-ui
sudo bash scripts/install-service.sh
```

常用指令：

```bash
sudo systemctl status pi5-whisper-ui.service
sudo journalctl -u pi5-whisper-ui.service -f
sudo systemctl restart pi5-whisper-ui.service
sudo systemctl stop pi5-whisper-ui.service
```

## 注意事項

- 請先確認 `deploy/systemd/pi5-whisper-ui.service` 的 `User` / `Group` 是否已改成你的帳號。
- 上傳檔名已做安全處理（僅取 basename，避免路徑穿越）。
- 任務資料夾名稱加入 UUID，避免同秒啟動時發生碰撞。
