"""任務狀態持久化管理。"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class JobStateStore:
    """以 JSON 檔管理目前任務狀態（單機單任務）。"""

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Optional[Dict[str, Any]]:
        if not self.state_path.exists():
            return None
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def save(self, state: Dict[str, Any]) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)

    @staticmethod
    def now_iso() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def mark_interrupted_if_stale(self, stale_seconds: int) -> Optional[Dict[str, Any]]:
        state = self.load()
        if not state or state.get("status") != "running":
            return state

        # 若目前仍有活著的 subprocess，不要標記 interrupted
        pid = int(state.get("current_pid") or 0)
        if self._pid_alive(pid):
            return state

        last_updated = state.get("last_updated")
        if not last_updated:
            return state

        try:
            last_dt = datetime.fromisoformat(last_updated)
        except ValueError:
            return state

        delta = datetime.now() - last_dt
        if delta.total_seconds() > stale_seconds:
            state["status"] = "interrupted"
            state["message"] = "偵測到殘留 running 狀態且長時間無更新，已標記為 interrupted。"
            state["end_time"] = self.now_iso()
            state["last_updated"] = self.now_iso()
            self.save(state)

        return state
