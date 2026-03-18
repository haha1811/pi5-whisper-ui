#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="pi5-whisper-ui.service"
PROJECT_DIR="/mnt/ssd/workspace/pi5-whisper-ui"
SERVICE_SRC="$PROJECT_DIR/deploy/systemd/$SERVICE_NAME"
SERVICE_DST="/etc/systemd/system/$SERVICE_NAME"

if [[ "${EUID}" -ne 0 ]]; then
  echo "[ERROR] 請用 sudo 執行：sudo bash scripts/install-service.sh"
  exit 1
fi

if [[ ! -f "$SERVICE_SRC" ]]; then
  echo "[ERROR] 找不到 service 範本：$SERVICE_SRC"
  exit 1
fi

echo "[INFO] 複製 service 檔到 $SERVICE_DST"
cp "$SERVICE_SRC" "$SERVICE_DST"

echo "[INFO] 重新載入 systemd"
systemctl daemon-reload

echo "[INFO] 啟用開機自啟"
systemctl enable "$SERVICE_NAME"

echo "[INFO] 立即啟動服務"
systemctl restart "$SERVICE_NAME"

echo "[INFO] 目前服務狀態"
systemctl --no-pager --full status "$SERVICE_NAME" || true

echo "[DONE] 安裝完成"
echo "- 查看 log: journalctl -u $SERVICE_NAME -f"
echo "- 重啟服務: sudo systemctl restart $SERVICE_NAME"
echo "- 停止服務: sudo systemctl stop $SERVICE_NAME"
