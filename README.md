# pi5-whisper-ui

在 Raspberry Pi 5 上執行的本機 Streamlit Web UI：把手機錄音檔 `.m4a` 自動轉成逐字稿 `.txt`。

## 專案目錄結構

```text
pi5-whisper-ui/
├─ app.py
├─ transcriber.py
├─ utils.py
├─ history.py                  # 使用紀錄 SQLite
├─ monitor.py                  # CPU / Memory 與核心數偵測
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
- threads 硬體感知：依 CPU 邏輯核心數限制最大值
- 動態顯示 Current Settings（選項一改就更新）
- 顯示目前 step、segment 進度與即時 log
- Sidebar System Monitor 每 60 秒自動更新 CPU/Memory，並顯示 Last updated 時間
- 完成後顯示音檔長度、處理時間、RTF
- Admin 頁面可查看歷史、刪除紀錄、刪除輸出資料夾、批次清理舊任務

## RTF（Real-time Factor）是什麼？

- 定義：`RTF = Processing Time / Audio Length`
- 範例：音檔 10 分鐘，處理 3 分鐘，RTF = `0.30x`
- 解讀：
  - `RTF < 1`：比即時播放更快
  - `RTF = 1`：約等於即時播放
  - `RTF > 1`：比即時播放慢

## Threads 與 CPU cores 建議

- App 啟動時會偵測 CPU 邏輯核心數（`psutil` 優先，無則用 `os.cpu_count()`）。
- threads 控制範圍：最小 1、最大 = CPU 邏輯核心數。
- 建議值：`threads = CPU 邏輯核心數`。
- 設太高不一定更快，可能增加系統負擔。

### Raspberry Pi 5 建議

- 若偵測到 4 核心，建議先使用 `threads = 4`。
- 若系統同時還跑其他工作，可先試 `threads = 3` 以保留餘裕。

## 使用紀錄（Usage History）

- 資料庫：`/mnt/ssd/workspace/pi5-whisper-ui/data/history.db`
- 每次成功轉寫會記錄：
  - timestamp
  - filename
  - model
  - language
  - cpu_logical_cores
  - threads_used
  - audio_duration_seconds
  - processing_time_seconds
  - rtf
  - output_directory

> 相容策略：若你已有舊版 DB，程式啟動時會自動補齊新欄位並搬移舊欄位資料，不需手動 migration。

## Admin 面板

在 Streamlit 側欄切換到 `Admin / Usage History` 頁面，可執行：

- 查看使用紀錄表格（含 audio duration / processing time / RTF）
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
