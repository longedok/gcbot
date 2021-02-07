from __future__ import annotations

import os
import logging
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from entities import Message, ValidationError

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from client import Client
    from collector import GarbageCollector
    from entities import Command

logger = logging.getLogger(__name__)

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
        logger.info("Starting the polling loop")
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
            "bot_uptime": _format_uptime(uptime),
        }

    def _reply(self, chat_id: int, text: str) -> None:
        logger.debug("Replying to chat %s: %s", chat_id, repr(text))
        self.client.post_message(chat_id, text)

    def dispatch_command(self, command: Command) -> None:
        if command.username and command.username != self.USERNAME:
            logger.debug(
                "Received command meant for another bot: %s@%s",
                command.command_str,
                command.username,
            )
            return  # don't process commands that wasn't meant for us

        if command.command_str not in self.COMMANDS:
            self._reply(
                command.chat_id, f"Unrecognized command: {command.command_str}"
            )
            return

        handler = getattr(self, f"process_{command.command_str}", None)
        if handler and callable(handler):
            try:
                command.clean_params()
                logger.info("Processing %s", command)
                handler(command)
            except ValidationError as exc:
                if exc.message:
                    self._reply(command.chat_id, exc.message)

    def process_gc(self, command: Command) -> None:
        if command.params_clean:
            ttl = command.params_clean[0]
        else:
            ttl = self.DEFAULT_TTL

        self.collector.enable(command.chat_id, ttl)
        logger.debug("GC enabled")

        self._reply(
            command.chat_id,
            f"Garbage collector enabled - automatically removing all new messages "
            f"after {ttl} seconds."
        )

    def process_gcoff(self, command: Command) -> None:
        self.collector.disable(command.chat_id)
        logger.debug("GC disabled")
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
        status_str = _format_status(status)
        self._reply(command.chat_id, f"Status: {status_str}")

    def process_ping(self, command: Command) -> None:
        self._reply(command.chat_id, f"pong")

    def process_github(self, command: Command) -> None:
        self._reply(command.chat_id, f"https://github.com/longedok/gcbot")

    def process_help(self, command: Command) -> None:
        self._reply(command.chat_id, HELP)


def _format_status(status: dict[str, Any]) -> str:
    return json.dumps(status, indent=4)


def _format_uptime(uptime: timedelta) -> str:
    uptime_str = str(uptime)
    time_str, _, _ = uptime_str.partition(".")
    return time_str

