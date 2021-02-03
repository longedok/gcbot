#!/usr/bin/env python3
from __future__ import annotations

import os
import requests
import logging
import time
import json
from datetime import datetime
from typing import Any, TYPE_CHECKING, TypeVar, Callable, cast
from threading import Thread, Lock
from dataclasses import dataclass
from functools import wraps

from db import init_storage, Session, session, MessageRecord, Settings

if TYPE_CHECKING:
    from datetime import timedelta

TOKEN = os.environ["TOKEN"]
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)-5s %(name)s > %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG,
)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

logger = logging.getLogger()


class Client:
    POLL_INTERVAL = 300

    def __init__(self, last_update_id: int | None = None) -> None:
        self.last_update_id = last_update_id

    def _post(self, url: str, data: dict) -> None:
        headers = {
            "Content-Type": "application/json",
        }
        response = requests.post(url, json=data, headers=headers)

        if response.status_code == 200:
            logger.debug("Got response: %s", response.text)
        else:
            logger.error(
                "Got non-200 response: %s %s", response.status_code, response.text
            )

    def _get(self, url: str, silent: bool = True, **params: Any) -> dict:
        headers = {
            "Content-Type": "application/json",
        }
        response = requests.get(url, params=params, headers=headers)
        if not silent:
            response.raise_for_status()

        if response.status_code != 200:
            logger.error(
                "Got non-200 response: %s %s", response.status_code, response.text,
            )
            return {}  # TODO: raise an exception

        try:
            data = response.json()
        except ValueError:
            logger.error("Got invalid json %s", response.text)
            return {}  # TODO: raise an exception

        if not data["ok"]:
            logger.error("Got non-ok response: %s", data)
            return {}  # TODO: raise an exception

        return data

    @property
    def offset(self) -> int | None:
        return self.last_update_id + 1 if self.last_update_id else None

    def get_updates(self) -> list[dict]:
        data = self._get(
            f"{BASE_URL}/getUpdates",
            timeout=self.POLL_INTERVAL,
            offset=self.offset,
            silent=False  # don't fail silently to avoid generating a lot of requests 
                          # in the polling loop
        )

        if updates := data.get("result", []):
            last_update = updates[-1]
            self.last_update_id = last_update["update_id"]

        return updates

    def post_message(self, chat_id: int, text: str) -> None:
        body = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        self._post(f"{BASE_URL}/sendMessage", body)

    def delete_message(self, chat_id: int, message_id: int) -> None:
        body = {
            "chat_id": chat_id,
            "message_id": message_id,
        }

        self._post(f"{BASE_URL}/deleteMessage", body)


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

    @no_sql_log
    def collect_garbage(self) -> None:
        now = int(datetime.now().timestamp())

        records = list(
            self.session
            .query(MessageRecord)
            .filter(
                MessageRecord.delete_after <= now,
                MessageRecord.deleted == False,
                MessageRecord.should_delete == True,
            )
        )

        if record_ids := [r.message_id for r in records]:
            logger.debug("Collected %s", record_ids)

        for record in records:
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
                MessageRecord.deleted == False,
                MessageRecord.should_delete == True,
            )
            .count()
        )

    def status(self, chat_id: int) -> dict[str, Any]:
        settings = self._get_settings(chat_id)
        return {
            "gc_enabled": settings.gc_enabled,
            "gc_ttl": settings.gc_ttl,
            "gc_pending_count": self.count_pending(chat_id),
        }


class ValidationError(Exception):
    def __init__(self, message: str | None) -> None:
        self.message = message


@dataclass
class Message:
    text: str | None
    message_id: int
    chat_id: int
    date: int
    entities: list[dict]

    @classmethod
    def from_json(cls, message_json: dict) -> Message:
        text = message_json.get("text")
        message_id = message_json["message_id"]
        chat_id = message_json["chat"]["id"]
        entities = message_json.get("entities", [])
        date = message_json["date"]

        return cls(text, message_id, chat_id, date, entities)

    def get_command(self) -> Command | None:
        commands = [e for e in self.entities if e["type"] == "bot_command"]
        entity = next(iter(commands), None)

        if not entity or not self.text:
            return None

        offset, length = entity["offset"], entity["length"]
        command_str = self.text[offset + 1:offset + length].lower()
        command_str, _, username = command_str.partition("@")

        params_str = self.text[offset + length + 1:]
        params = params_str.split() if params_str else []

        return Command(command_str, params, username, offset, self)


@dataclass
class Command:
    command_str: str
    params: list[str]
    username: str
    offset: int
    message: Message

    @property
    def chat_id(self) -> int:
        return self.message.chat_id


HELP = """
This bot allows you to set an expiration time for all new messages in a group chat.

Supported commands:

/gc <i>ttl</i> - Enable automatic removal of messages after <i>ttl</i> seconds, e.g. <code>/gc 3600</code> to remove new messages after 1 hour. Default <i>ttl</i> is 86400 seconds (1 day).
/gcoff - Disable automatic removal of messages.
/cancel - Cancel removal of all pending messages.
/status - Get current status.
/github - Link to the bot's source code.
/ping - Sends "pong" in response.
/help - Display help message.
"""


class Bot:
    USERNAME = os.environ.get("BOT_USERNAME", "gcservantbot")
    COMMANDS = [
        "gc",
        "gcoff",
        "cancel",
        "status",
        "ping",
        "github",
        "help",
    ]
    DEFAULT_TTL = 86400

    def __init__(self, client: Client, collector: GarbageCollector) -> None:
        self.client = client
        self.collector = collector
        self.start_at = datetime.now()

    def start(self) -> None:
        while True:
            try:
                updates = self.client.get_updates()
            except KeyboardInterrupt:
                logger.info("Exiting...")
                return

            for update in updates:
                logger.debug("Got new update: %s", update)
                if "message" in update:
                    message = Message.from_json(update["message"])
                    self.process_message(message)

    def process_message(self, message: Message) -> None:
        logger.debug("Processing %s", message)
        command = message.get_command()
        if command and command.offset == 0:
            self.dispatch_command(command)
            return

        self.collector.add_message(message)

    def _get_uptime(self) -> timedelta:
        return datetime.now() - self.start_at

    def status(self) -> dict[str, Any]:
        uptime = self._get_uptime()
        return {
            "bot_uptime": format_uptime(uptime),
        }

    def _reply(self, chat_id: int, text: str) -> None:
        self.client.post_message(chat_id, text)

    def dispatch_command(self, command: Command) -> None:
        if command.username and command.username != self.USERNAME:
            return  # don't process commands that aren't meant for us

        logger.info(
            "Got new command: '%s' with params %s", command.command_str, command.params
        )

        if command.command_str not in self.COMMANDS:
            self._reply(
                command.chat_id, f"Unrecognized command: {command.command_str}"
            )
            return

        handler = getattr(self, f"process_{command.command_str}", None)
        if handler and callable(handler):
            try:
                handler(command)
            except ValidationError as exc:
                if exc.message:
                    self._reply(command.chat_id, exc.message)

    def process_gc(self, command: Command) -> None:
        if command.params:
            ttl_raw = command.params[0]
            try:
                ttl = int(ttl_raw)
                if not (0 <= ttl <= 172800):
                    raise ValueError
            except (TypeError, ValueError):
                raise ValidationError(
                    "Please provide a \"time to live\" for messages as a valid "
                    "integer between 0 and 172800.\n"
                    "E.g. \"/gcon 3600\" to start removing new messages after one "
                    "hour."
                )
        else:
            ttl = self.DEFAULT_TTL

        self.collector.enable(command.chat_id, ttl)
        logging.debug("GC enabled")

        self._reply(
            command.chat_id,
            f"Garbage collector enabled - automatically removing all new messages "
            f"after {ttl} seconds."
        )

    def process_gcoff(self, command: Command) -> None:
        self.collector.disable(command.chat_id)
        logging.debug("GC disabled")
        self._reply(
            command.chat_id,
            "Garbage collector disabled - "
            "new messages won't be removed automatically."
        )

    def process_cancel(self, command: Command) -> None:
        cancelled = self.collector.cancel(command.chat_id)
        self._reply(
            command.chat_id, f"Cancelled removal of {cancelled} pending messages."
        )

    def process_status(self, command: Command) -> None:
        status = self.collector.status(command.chat_id)
        status.update(self.status())
        status_str = format_status(status)
        self._reply(command.chat_id, f"Status: {status_str}")

    def process_ping(self, command: Command) -> None:
        self._reply(command.chat_id, f"pong")

    def process_github(self, command: Command) -> None:
        self._reply(command.chat_id, f"https://github.com/longedok/gcbot")

    def process_help(self, command: Command) -> None:
        self._reply(command.chat_id, HELP)


def format_status(status: dict[str, Any]) -> str:
    return json.dumps(status, indent=4)


def format_uptime(uptime: timedelta) -> str:
    uptime_str = str(uptime)
    time_str, _, _ = uptime_str.partition(".")
    return time_str


def main() -> None:
    init_storage()

    client = Client()

    collector = GarbageCollector(client)
    collector.start()

    bot = Bot(client, collector)
    bot.start()


if __name__ == "__main__":
    main()

