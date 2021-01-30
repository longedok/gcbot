#!/usr/bin/env python3
from __future__ import annotations

import os
import requests
import logging
import time
import json
from datetime import datetime
from typing import Any
from threading import Thread
from dataclasses import dataclass

from db import init_storage, Message, Settings, session, Session

TOKEN = os.environ["TOKEN"]
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)-5s %(name)s > %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG,
)

logger = logging.getLogger()


class UpdatesPoller:
    POLL_INTERVAL = 300

    def __init__(self, last_update_id: int | None = None) -> None:
        self.last_update_id = last_update_id

    def _get(self, url: str, **params: Any) -> dict:
        headers = {
            "Content-Type": "application/json",
        }
        response = requests.get(url, params=params, headers=headers)

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

        return data

    @property
    def offset(self) -> int | None:
        return self.last_update_id + 1 if self.last_update_id else None

    def get_updates(self) -> list[dict]:
        data = self._get(
            f"{BASE_URL}/getUpdates",
            timeout=self.POLL_INTERVAL,
            offset=self.offset
        )

        if not data["ok"]:
            logger.error("Got non-ok response: %s", data)
            return []  # TODO: raise an exception

        updates = data["result"]
        if updates:
            last_update = updates[-1]
            self.last_update_id = last_update["update_id"]

        return updates


class Client:
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

    def post_message(self, chat_id: int, text: str) -> None:
        body = {
            "chat_id": chat_id,
            "text": text,
        }

        self._post(f"{BASE_URL}/sendMessage", body)

    def delete_message(self, chat_id: int, message_id: int) -> None:
        body = {
            "chat_id": chat_id,
            "message_id": message_id,
        }

        self._post(f"{BASE_URL}/deleteMessage", body)


class GarbageCollector(Thread):
    def __init__(
        self,
        client: Client,
    ) -> None:
        super().__init__(daemon=True)

        self.client = client

        settings = self._get_settings()
        self.enabled = settings.gc_enabled
        self.ttl = settings.gc_ttl

    def _get_settings(self) -> Settings:
        return session.query(Settings).first()

    def enable(self, ttl: int) -> None:
        self.enabled = True
        self.ttl = ttl

        settings = self._get_settings()
        settings.gc_enabled = self.enabled
        settings.gc_ttl = self.ttl
        session.add(settings)
        session.commit()

    def disable(self) -> None:
        self.enabled = False
        settings = self._get_settings()
        settings.gc_enabled = False
        session.add(settings)
        session.commit()

    def add_message(self, message_data: dict) -> None:
        if not self.enabled:
            return

        message = Message(
            message_id=message_data["message_id"],
            chat_id=message_data["chat"]["id"],
            delete_after=message_data["date"] + self.ttl,
        )
        session.add(message)
        session.commit()

    def collect_garbage(self) -> None:
        threshold = int(datetime.now().timestamp())
        messages = (
            self.session
            .query(Message)
            .filter(Message.delete_after <= threshold, Message.deleted == False)
        )

        mids = [m.message_id for m in messages]
        if mids:
            logger.debug("Collected %s", mids)

        for message in messages:
            self.client.delete_message(message.chat_id, message.message_id)
            message.deleted = True
            self.session.add(message)

        self.session.commit()

    def run(self) -> None:
        self.session = Session()
        while True:
            self.collect_garbage()
            time.sleep(1)

    def count_pending(self) -> int:
        return (
            session.query(Message)
            .filter(Message.deleted == False)
            .count()
        )

    def status(self) -> dict[str, Any]:
        return {
            "gc_enabled": self.enabled,
            "gc_ttl": self.ttl,
            "gc_pending_count": self.count_pending(),
        }


class ValidationError(Exception):
    def __init__(self, message: str | None) -> None:
        self.message = message


@dataclass
class Command:
    command: str
    params: list[str]
    username: str
    message: dict

    @property
    def chat_id(self) -> int:
        return self.message["chat"]["id"]

    @classmethod
    def from_message_and_entity(self, message: dict, entity: dict) -> Command:
        text = message["text"]
        offset, length = entity["offset"], entity["length"]

        command = text[offset + 1:offset + length].lower()
        command, _, username = command.partition("@")

        params_str = text[offset + length + 1:]
        params = params_str.split() if params_str else []

        return Command(command, params, username, message)


class Bot:
    USERNAME = "gcservantbot"
    COMMANDS = [
        "gcon",
        "gcoff",
        "status",
        "ping",
        "github",
    ]
    DEFAULT_TTL = 86400

    def __init__(self, client: Client, gc: GarbageCollector) -> None:
        self.client = client
        self.gc = gc

    def start(self) -> None:
        poller = UpdatesPoller()
        while True:
            try:
                updates = poller.get_updates()
            except KeyboardInterrupt:
                logger.info("Exiting...")
                return

            for update in updates:
                logger.debug("Got new update: %s", update)
                if "message" in update:
                    self.dispatch_message(update["message"])

    def dispatch_message(self, message: dict) -> None:
        entities = message.get("entities", [])
        commands = [e for e in entities if e["type"] == "bot_command"]
        command_entity = next(iter(commands), None)

        if command_entity and command_entity["offset"] == 0:
            self.dispatch_command(message, command_entity)
        else:
            self.process_message(message)

    def dispatch_command(self, message: dict, entity: dict) -> None:
        command = Command.from_message_and_entity(message, entity)

        if command.username and command.username != self.USERNAME:
            return  # don't process commands that aren't meant for us

        logger.info(
            "Got new command: '%s' with params %s", command.command, command.params
        )

        if command.command not in self.COMMANDS:
            self.client.post_message(
                command.chat_id, f"Unrecognized command: {command.command}"
            )
            return

        handler = getattr(self, f"process_{command.command}", None)
        if handler and callable(handler):
            try:
                handler(command)
            except ValidationError as exc:
                if exc.message:
                    self.client.post_message(command.chat_id, exc.message)

    def process_message(self, message: dict) -> None:
        logger.debug("Processing regular chat message")
        self.gc.add_message(message)

    def process_gcon(self, command: Command) -> None:
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

        self.gc.enable(ttl)
        logging.debug("GC enabled")

        self.client.post_message(
            command.chat_id,
            f"Garbage collector enabled - automatically removing all new messages "
            f"after {ttl} seconds."
        )

    def process_gcoff(self, command: Command) -> None:
        self.gc.disable()
        logging.debug("GC disabled")

        self.client.post_message(
            command.chat_id,
            "Garbage collector disabled - "
            "new messages won't be removed automatically"
        )

    def process_status(self, command: Command) -> None:
        status = json.dumps(self.gc.status(), indent=4)

        self.client.post_message(command.chat_id, f"Status: {status}")

    def process_ping(self, command: Command) -> None:
        self.client.post_message(command.chat_id, f"Pong")

    def process_github(self, command: Command) -> None:
        self.client.post_message(command.chat_id, f"https://github.com/longedok/gcbot")


def main() -> None:
    init_storage()

    client = Client()
    gc = GarbageCollector(client)
    gc.start()

    bot = Bot(client, gc)
    bot.start()


if __name__ == "__main__":
    main()

