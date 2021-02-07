from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, TypeVar, Callable, Any, cast
from functools import wraps
from threading import Thread

from db import Session, Settings, MessageRecord, session

if TYPE_CHECKING:
    from client import Client
    from entities import Message

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def no_sql_log(func: F) -> F:
    @wraps(func)
    def inner(*args, **kwargs):  # type: ignore
        logger = logging.getLogger('sqlalchemy.engine')
        level = logger.level

        logger.setLevel(logging.WARNING)
        result = func(*args, **kwargs)
        logger.setLevel(level)

        return result

    return cast(F, inner)


class GarbageCollector(Thread):
    MAX_HOURS = 48  # maximum time during which it's allowed to delete messages

    def __init__(self, client: Client) -> None:
        super().__init__(daemon=True)
        self.client = client

    def _get_settings(self, chat_id: int) -> Settings:
        settings = session.query(Settings).filter(
            Settings.chat_id == chat_id,
        ).first()

        if not settings:
            settings = Settings(chat_id=chat_id)
            session.add(settings)
            session.commit()

        return settings

    def enable(self, chat_id: int, ttl: int) -> None:
        settings = self._get_settings(chat_id)
        settings.gc_enabled = True
        settings.gc_ttl = ttl
        session.add(settings)
        session.commit()

    def disable(self, chat_id: int) -> None:
        settings = self._get_settings(chat_id)
        settings.gc_enabled = False
        session.add(settings)
        session.commit()

    def cancel(self, chat_id: int) -> int:
        cancelled = session.query(MessageRecord).filter(
            MessageRecord.chat_id == chat_id,
            MessageRecord.deleted == False,
            MessageRecord.should_delete == True,
        ).update({"should_delete": False})

        session.commit()

        return cancelled

    def add_message(self, message: Message) -> None:
        settings = self._get_settings(message.chat_id)
        now = int(datetime.now().timestamp())
        delete_after = now + settings.gc_ttl if settings.gc_enabled else None
        record = MessageRecord(
            chat_id=message.chat_id,
            message_id=message.message_id,
            date=message.date,
            delete_after=delete_after,
            should_delete=settings.gc_enabled,
        )
        session.add(record)
        session.commit()

    @property
    def unreachable_date(self) -> int:
        date = datetime.now() - timedelta(hours=self.MAX_HOURS)
        return int(date.timestamp())

    @no_sql_log
    def collect_garbage(self) -> None:
        now = int(datetime.now().timestamp())

        records = list(
            self.session
            .query(MessageRecord)
            .filter(
                MessageRecord.delete_after <= now,
                MessageRecord.deleted == False,
                MessageRecord.date > self.unreachable_date,
                MessageRecord.should_delete == True,
            )
        )

        if record_ids := [r.message_id for r in records]:
            logger.debug("Collected %s", record_ids)

        for record in records:
            logger.debug("Deleting message %s %s", record.chat_id, record.message_id)
            self.client.delete_message(record.chat_id, record.message_id)
            record.deleted = True
            self.session.add(record)

        self.session.commit()

    def run(self) -> None:
        self.session = Session()
        while True:
            self.collect_garbage()
            time.sleep(1)

    def count_pending(self, chat_id: int) -> int:
        return (
            session.query(MessageRecord)
            .filter(
                MessageRecord.chat_id == chat_id,
                MessageRecord.date > self.unreachable_date,
                MessageRecord.deleted == False,
                MessageRecord.should_delete == True,
            )
            .count()
        )

    def count_unreachable(self, chat_id: int) -> int:
        return (
            session.query(MessageRecord)
            .filter(
                MessageRecord.chat_id == chat_id,
                MessageRecord.date <= self.unreachable_date,
                MessageRecord.deleted == False,
            )
            .count()
        )

    def status(self, chat_id: int) -> dict[str, Any]:
        settings = self._get_settings(chat_id)
        return {
            "gc_enabled": settings.gc_enabled,
            "gc_ttl": settings.gc_ttl,
            "gc_pending_count": self.count_pending(chat_id),
            "gc_unreachable_count": self.count_unreachable(chat_id),
        }

