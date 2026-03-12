"""系統監控與硬體資訊。"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, Tuple


def get_cpu_logical_cores() -> int:
    """取得邏輯核心數，至少回傳 1。"""
    try:
        import psutil  # type: ignore

        cores = psutil.cpu_count(logical=True)
        if cores and cores > 0:
            return int(cores)
    except Exception:  # noqa: BLE001
        pass

    fallback = os.cpu_count() or 1
    return max(1, int(fallback))


def get_system_usage() -> Optional[Tuple[float, float]]:
    """回傳 (cpu_percent, memory_percent)，若 psutil 不可用則回傳 None。"""
    try:
        import psutil  # type: ignore
    except Exception:  # noqa: BLE001
        return None

    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory().percent
    return cpu, mem


def get_system_usage_with_timestamp() -> Optional[Tuple[float, float, str]]:
    """回傳 (cpu_percent, memory_percent, HH:MM:SS)。"""
    usage = get_system_usage()
    if usage is None:
        return None
    cpu, mem = usage
    return cpu, mem, datetime.now().strftime("%H:%M:%S")
