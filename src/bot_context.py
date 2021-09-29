from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import timedelta


class BotContext:
    def __init__(self) -> None:
        self.start_at = datetime.now()

    def get_uptime(self) -> timedelta:
        return datetime.now() - self.start_at
