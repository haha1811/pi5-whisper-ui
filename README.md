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
5. 視需求勾選是否保留中間檔。
6. 確認輸出目錄後按「開始轉寫」。
7. 等待流程完成，預覽結果並下載最終 `.txt`。

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
