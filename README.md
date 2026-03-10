# pi5-whisper-ui

在 Raspberry Pi 5 上執行的本機 Streamlit Web UI：把手機錄音檔 `.m4a` 自動轉成逐字稿 `.txt`。

## 專案目錄結構

```text
pi5-whisper-ui/
├─ app.py                # Streamlit 單頁 UI
├─ transcriber.py        # 轉檔/切段/轉寫/合併 核心流程
├─ utils.py              # 通用工具（logger、subprocess、目錄管理）
├─ config.py             # 路徑與預設值集中設定
├─ requirements.txt      # Python 依賴
└─ README.md             # 說明文件
```

## 功能

- 上傳 `.m4a` 檔
- 設定切段長度（預設 15 分鐘）
- 選擇模型（small / medium / large-v3-turbo）
- 選擇辨識語言（auto / zh / en / ja，預設 zh）
- 可設定 whisper 執行緒數（threads）
- 可選擇是否保留中間檔
- 顯示目前步驟與進度
- 顯示錯誤訊息與執行 log
- 完成後預覽逐字稿並下載 `.txt`
- 頁面載入時與開始前都會檢查模型檔是否存在

## 先決條件

請先確認 Raspberry Pi 5 上已安裝：

- Python 3.10+
- `ffmpeg`
- `whisper.cpp`

並且模型檔存在：

- `/mnt/ssd/tools/whisper.cpp/models/ggml-small.bin`
- `/mnt/ssd/tools/whisper.cpp/models/ggml-medium.bin`
- `/mnt/ssd/tools/whisper.cpp/models/ggml-large-v3-turbo.bin`

## 安裝

```bash
cd /workspace/pi5-whisper-ui
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 啟動

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

啟動後在同網段裝置開啟：

```text
http://<你的_pi_ip>:8501
```

## 使用方式

1. 開啟網頁後先看「模型檢查」是否皆為綠色可用。
2. 上傳 `.m4a` 檔案。
3. 設定分段長度（建議先維持 15 分鐘）。
4. 選擇模型（預設 `small`，Pi5 較穩定）。
5. 選擇辨識語言（建議中文錄音使用 `zh`）。
6. 視硬體狀況調整執行緒數（threads）。
7. 視需求勾選是否保留中間檔。
8. 確認輸出目錄後按「開始轉寫」。
9. 等待流程完成，預覽結果並下載最終 `.txt`。


## 語言選擇說明

- `zh`：中文錄音建議使用，避免被誤判為英文。
- `en`：英文錄音。
- `ja`：日文錄音。
- `auto`：不帶 `-l` 參數，讓 whisper 自動判斷語言。

當你在 UI 選擇語言後，程式會在呼叫 `whisper-cli` 時自動套用：

- `zh` -> `-l zh`
- `en` -> `-l en`
- `ja` -> `-l ja`
- `auto` -> 不加 `-l`

## 路徑與設定調整

所有主要路徑都集中在 `config.py`：

- `whisper_cpp_root`
- `models_root`
- `output_root`
- `log_root`
- `default_segment_minutes`
- `default_model_name`

## 測試方式（手動）

1. 準備一個短音檔 `demo.m4a`。
2. 進 UI 上傳並執行。
3. 檢查是否產生：
   - 輸出目錄下的任務資料夾
   - `final_transcript.txt`
   - logs 目錄中的 `.log`
4. 驗證下載的 txt 內容是否合理。

## 架構說明（為何適合 Pi5）

- **簡單可維護**：流程集中在 `TranscriptionPipeline`，UI 與邏輯分離。
- **資源可控**：以分段方式處理長音檔，避免一次吃滿記憶體。
- **保留既有能力**：直接呼叫你已可用的 `ffmpeg` 與 `whisper.cpp`，不重寫辨識核心。
- **路徑集中管理**：非程式背景也能在 `config.py` 直接調整環境。


## systemd 開機自動啟動（Raspberry Pi 5 + SSD）

以下指令都以實際專案路徑為準：
`/mnt/ssd/workspace/pi5-whisper-ui`

### 1) service 檔名稱

建議使用：`pi5-whisper-ui.service`

### 2) 範本檔位置

本專案已提供：

- `deploy/systemd/pi5-whisper-ui.service`
- `scripts/install-service.sh`

### 3) 先確認 service 內的執行使用者

打開 `deploy/systemd/pi5-whisper-ui.service`，將：

- `User=haha`
- `Group=haha`

改成你 Pi 上實際要跑服務的帳號（例如 `pi` 或你的自訂帳號）。

### 4) 安裝 service（建議）

```bash
cd /mnt/ssd/workspace/pi5-whisper-ui
sudo bash scripts/install-service.sh
```

### 5) 手動安裝方式（不使用腳本）

```bash
sudo cp /mnt/ssd/workspace/pi5-whisper-ui/deploy/systemd/pi5-whisper-ui.service /etc/systemd/system/pi5-whisper-ui.service
sudo systemctl daemon-reload
sudo systemctl enable pi5-whisper-ui.service
sudo systemctl start pi5-whisper-ui.service
```

### 6) 常用管理指令

```bash
# 狀態
sudo systemctl status pi5-whisper-ui.service

# 持續看 log
sudo journalctl -u pi5-whisper-ui.service -f

# 最近 200 行 log
sudo journalctl -u pi5-whisper-ui.service -n 200 --no-pager

# 重啟 / 停止 / 啟動
sudo systemctl restart pi5-whisper-ui.service
sudo systemctl stop pi5-whisper-ui.service
sudo systemctl start pi5-whisper-ui.service
```

### 7) 設計重點與注意事項

- `WorkingDirectory` 已固定為 `/mnt/ssd/workspace/pi5-whisper-ui`。
- `ExecStart` 使用 venv 內 Python：
  `/mnt/ssd/workspace/pi5-whisper-ui/.venv/bin/python -m streamlit ...`
- 使用 `RequiresMountsFor=/mnt/ssd/...`，可降低開機時 SSD 尚未掛載導致啟動失敗的機率。
- `Restart=on-failure` + `StartLimitIntervalSec/StartLimitBurst`，避免例外時無限快速重啟。
- `--server.headless true` 與 `STREAMLIT_SERVER_HEADLESS=true` 已一併設定，適合背景服務。

