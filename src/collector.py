from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, TypeVar, Callable, Any, cast
from functools import wraps
from threading import Thread
from queue import Queue, Empty

from db import Session, MessageRecord, session as global_session
from settings import get_settings
from utils import format_interval

if TYPE_CHECKING:
    from client import Client
    from entities import Message
    from sqlalchemy.orm import Query
    from sqlalchemy.orm.session import Session as SessionType

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
    MAX_HOURS = 48  # maximum time during which a message can be deleted after 
                    # it's posted

    def __init__(self, client: Client) -> None:
        super().__init__(daemon=True)
        self.client = client
        self.retries_queue: Queue[tuple[int, int | None]] = Queue()

    def enable(self, chat_id: int, ttl: int) -> None:
        logger.debug(
            "Enabling garbage collector for chat %s with ttl %ss", chat_id, ttl
        )
        settings = get_settings(chat_id)
        settings.gc_enabled = True
        settings.gc_ttl = ttl
        global_session.add(settings)
        global_session.commit()

    def disable(self, chat_id: int) -> None:
        logger.debug("Disabling garbage collector for chat %s", chat_id)
        settings = get_settings(chat_id)
        settings.gc_enabled = False
        global_session.add(settings)
        global_session.commit()

    def cancel(self, chat_id: int) -> int:
        logger.debug("Cancelling removal of pending messages in chat %s", chat_id)
        cancelled = global_session.query(MessageRecord).filter(
            MessageRecord.chat_id == chat_id,
            MessageRecord.deleted == False,
            MessageRecord.should_delete == True,
        ).update({"should_delete": False, "delete_cancelled": True})

        global_session.commit()

        return cancelled

    def add_message(self, message: Message, ttl: int | None = None) -> None:
        logger.debug("Adding message %s to the grabage collector", message.message_id)

        delete_after, should_delete = None, False
        if ttl is None:
            settings = get_settings(message.chat_id)
            if settings.gc_enabled:
                delete_after = message.date + settings.gc_ttl
                should_delete = True
        else:
            delete_after = message.date + ttl
            should_delete = True

        record = MessageRecord(
            chat_id=message.chat_id,
            message_id=message.message_id,
            date=message.date,
            delete_after=delete_after,
            should_delete=should_delete,
        )
        global_session.add(record)
        global_session.commit()

    def run(self) -> None:
        self.thread_session = Session()
        while True:
            self.collect_garbage()
            try:
                retry_params = self.retries_queue.get(timeout=1)
            except Empty:
                continue
            chat_id, max_attempts = retry_params
            self._run_retry(chat_id, max_attempts)

    @property
    def unreachable_date(self) -> int:
        date = datetime.now() - timedelta(hours=self.MAX_HOURS)
        return int(date.timestamp())

    def _delete_record(self, record: MessageRecord) -> None:
        logger.debug(
            "Deleting message %s from chat %s", record.message_id, record.chat_id
        )

        response = self.client.delete_message(record.chat_id, record.message_id)

        record.delete_attempt += 1
        if response.ok:
            record.deleted = True
        else:
            record.should_delete = False
            record.deleted = False
            record.delete_failed = True
            logger.error(
                "Failed to delete message %s: %s", record.message_id, response,
            )

        self.thread_session.add(record)
        self.thread_session.commit()

    @no_sql_log
    def collect_garbage(self) -> None:
        now = int(datetime.now().timestamp())
        records = list(
            self.thread_session
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
            self._delete_record(record)

    def retry(self, chat_id: int, max_attempts: int | None = None) -> None:
        # Not running retry process directly in order to not block bot's polling loop.
        # Instead, use a queue to execute retries in the collector's thread.
        self.retries_queue.put((chat_id, max_attempts))

    def _run_retry(self, chat_id: int, max_attempts: int | None = None) -> None:
        logger.debug("Re-trying to delete failed messages for chat %s", chat_id)

        failed = list(
            self._get_failed(
                chat_id, max_attempts=max_attempts, session=self.thread_session,
            )
        )

        deleted_count, total = 0, len(failed)
        for record in failed:
            self._delete_record(record)
            if record.deleted:
                deleted_count += 1

        self.client.post_message(
            chat_id,
            f"Deleted {deleted_count} message(s) out of {total} after re-trying."
        )

    def get_removal_queue(self, chat_id: int) -> Query:
        records = (
            global_session.query(MessageRecord)
            .filter(
                MessageRecord.chat_id == chat_id,
                MessageRecord.date > self.unreachable_date,
                MessageRecord.deleted == False,
                MessageRecord.should_delete == True,
            )
            .order_by(MessageRecord.delete_after.asc())
        )

        return records

    def count_pending(self, chat_id: int) -> int:
        return (
            global_session.query(MessageRecord)
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
            global_session.query(MessageRecord)
            .filter(
                MessageRecord.chat_id == chat_id,
                MessageRecord.date <= self.unreachable_date,
                MessageRecord.deleted == False,
            )
            .count()
        )

    def count_cancelled(self, chat_id: int) -> int:
        return (
            global_session.query(MessageRecord)
            .filter(
                MessageRecord.chat_id == chat_id,
                MessageRecord.date > self.unreachable_date,
                MessageRecord.deleted == False,
                MessageRecord.delete_cancelled == True,
            )
            .count()
        )

    def count_deleted(self, chat_id: int) -> int:
        return (
            global_session.query(MessageRecord)
            .filter(
                MessageRecord.chat_id == chat_id,
                MessageRecord.deleted == True,
            )
            .count()
        )

    def next_delete_in(self, chat_id: int) -> timedelta | None:
        next_record = (
            global_session.query(MessageRecord)
            .filter(
                MessageRecord.chat_id == chat_id,
                MessageRecord.date > self.unreachable_date,
                MessageRecord.deleted == False,
                MessageRecord.should_delete == True,
            )
            .order_by(MessageRecord.delete_after)
            .first()
        )

        if not next_record:
            return None

        return datetime.utcfromtimestamp(next_record.delete_after) - datetime.utcnow()

    def _get_failed(
        self,
        chat_id: int,
        max_attempts: int | None = None,
        session: SessionType | None = None,
    ) -> Query:
        if session is None:
            session = global_session

        query = (
            session.query(MessageRecord)
            .filter(
                MessageRecord.chat_id == chat_id,
                MessageRecord.date > self.unreachable_date,
                MessageRecord.deleted == False,
                MessageRecord.delete_failed == True,
            )
        )

        if max_attempts is not None:
            query = query.filter(MessageRecord.delete_attempt <= max_attempts)

        return query

    def count_failed(self, chat_id: int, max_attempts: int | None = None) -> int:
        return self._get_failed(chat_id, max_attempts).count()

    def status(self, chat_id: int) -> dict[str, Any]:
        settings = get_settings(chat_id)
        next_delete_in = self.next_delete_in(chat_id)
        next_delete_str = format_interval(next_delete_in) if next_delete_in else "N/A"
        return {
            "gc_enabled": settings.gc_enabled,
            "gc_ttl": settings.gc_ttl,
            "gc_pending_count": self.count_pending(chat_id),
            "gc_unreachable_count": self.count_unreachable(chat_id),
            "gc_cancelled_count": self.count_cancelled(chat_id),
            "gc_failed_count": self.count_failed(chat_id),
            "gc_deleted_count": self.count_deleted(chat_id),
            "gc_next_delete_in": next_delete_str,
        }

