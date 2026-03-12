"""系統監控資訊（可選）。"""

from __future__ import annotations

from typing import Optional, Tuple


def get_system_usage() -> Optional[Tuple[float, float]]:
    """回傳 (cpu_percent, memory_percent)，若 psutil 不可用則回傳 None。"""
    try:
        import psutil  # type: ignore
    except Exception:  # noqa: BLE001
        return None

    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory().percent
    return cpu, mem
