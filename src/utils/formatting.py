from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import timedelta


def format_interval(interval: timedelta) -> str:
    uptime_str = str(interval)
    time_str, _, _ = uptime_str.partition(".")
    return time_str
