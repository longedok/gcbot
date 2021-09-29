from __future__ import annotations

import json
import math
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING, Iterable, cast

from .formatting import format_interval

if TYPE_CHECKING:
    from sqlalchemy.orm import Query

    from db import MessageRecord


class Table:
    PAGE_SIZE = 10

    def __init__(self, records: Query, page: int) -> None:
        self.records = records
        self.page = page

    @cached_property
    def total(self) -> int:
        return self.records.count()

    @cached_property
    def num_pages(self) -> int:
        return math.ceil(self.total / self.PAGE_SIZE)

    def build(self) -> str:
        if not self.total:
            return self.get_empty_message()

        offset = (self.page - 1) * self.PAGE_SIZE
        records = self.records.offset(offset).limit(self.PAGE_SIZE)

        table = self.get_title()
        rows = self.get_rows(records, offset)
        table += "\n".join(rows)
        table += f"\n\n[page <b>{self.page}</b> out of <b>{self.num_pages}</b>]"

        return table

    def get_title(self) -> str:
        return f"Message IDs to be deleted next (<b>{self.total}</b> in total):\n\n"

    def get_rows(self, records: Iterable[MessageRecord], offset: int) -> list[str]:
        rows = []
        utc_now = datetime.utcnow()
        for i, record in enumerate(records):
            delete_in = format_interval(
                datetime.utcfromtimestamp(record.delete_after or 0) - utc_now
            )
            row_number = offset + i + 1
            rows.append(f"{row_number}. <b>{record.message_id}</b> in {delete_in}")
        return rows

    def get_empty_message(self) -> str:
        return "No messages queued for removal."

    def _get_keyboard(self) -> list[list[dict]]:
        keyboard: list[list[dict]] = [[]]

        format_data = lambda page: json.dumps({"page": page, "type": "queue"})

        if self.page > 1:
            keyboard[0].append(
                {
                    "text": "<< prev",
                    "callback_data": format_data(self.page - 1),
                }
            )

        if self.page < self.num_pages:
            keyboard[0].append(
                {
                    "text": "next >>",
                    "callback_data": format_data(self.page + 1),
                }
            )

        return keyboard

    def get_reply_markup(self) -> dict:
        if self.num_pages <= 1:
            return {}

        return {
            "reply_markup": {
                "inline_keyboard": self._get_keyboard(),
            }
        }
