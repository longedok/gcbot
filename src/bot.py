from __future__ import annotations

import os
import logging
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from entities import Message, ValidationError
from utils import format_interval

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from client import Client
    from collector import GarbageCollector
    from entities import Command

logger = logging.getLogger(__name__)

HELP = """
This bot allows you to set an expiration time for all new messages in a group chat. It supports the following commands:

<b>Bot control</b>
/gc [<i>time_interval</i>] - Enable automatic removal of messages after <i>time_interval</i>. E.g., the command <code>/gc 1h</code> will result in all new messages being removed when they become 1 hour old.

The <i>time_interval</i> parameter accepts an integer value of seconds between 0 and 172800 or a string describing a time interval, such as "15 minutes" or "1h30m", up to the maximum value of "2 days". If the parameter is not provided, the default time intervals will be presented.

/gcoff - Disable automatic removal of messages.

/cancel - Cancel removal of all pending messages.

/retry [<i>max_attempts</i>] - Try to remove messages that failed to be removed automatically. If the <i>max_attempts</i> parameters is specified, messages that were already re-tried more than <i>max_attempts</i> times won't be re-tried.

<b>Bot info</b>
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
        "retry",
        "status",
        "ping",
        "github",
        "help",
        "noop",
    ]

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

            if updates:
                logger.debug("Got %s new update(s)", len(updates))

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

    def dispatch_command(self, command: Command) -> None:
        if command.username and command.username != self.USERNAME:
            logger.debug(
                "Received a command that's meant for another bot: %s@%s",
                command.command_str,
                command.username,
            )
            return  # don't process commands that wasn't meant for us

        if command.command_str not in self.COMMANDS:
            self._reply(
                command, f"Unrecognized command: {command.command_str}"
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
                    self._reply(command, exc.message)

    def _reply(self, command: Command, text: str, **kwargs: Any) -> None:
        chat_id = command.message.chat_id
        reply_to = command.message.message_id

        logger.debug("Replying to chat %s: %r", chat_id, text)

        self.client.post_message(
            chat_id, text, reply_to_message_id=reply_to, **kwargs,
        )

    def _get_gc_keyboard(self) -> dict[str, Any]:
        buttons = [
            [
                {"text": "/gc 30 seconds"},
                {"text": "/gc 5 minutes"},
            ],
            [
                {"text": "/gc 30 minutes"},
                {"text": "/gc 6 hours"},
            ],
            [
                {"text": "/gc 1 day"},
                {"text": "/gc 1 day 16 hours"},
            ],
            [
                {"text": "/gcoff - disable GC"},
                {"text": "/noop - cancel"}
            ]
        ]

        return {
            "keyboard": buttons,
            "one_time_keyboard": True,
            "selective": True,
        }

    def _get_remove_keyboard(self) -> dict[str, Any]:
        return {
            "remove_keyboard": True,
            "selective": True,
        }

    def process_gc(self, command: Command) -> None:
        if not command.params_clean:
            self._reply(
                command,
                "Please choose an expiration time for new messages",
                reply_markup=self._get_gc_keyboard(),
            )
            return

        ttl = command.params_clean[0]

        self.collector.enable(command.chat_id, ttl)
        logger.debug("GC enabled")

        self._reply(
            command,
            f"Garbage collector enabled - automatically removing all new messages "
            f"after {ttl} seconds.",
            reply_markup=self._get_remove_keyboard(),
        )

    def process_gcoff(self, command: Command) -> None:
        self.collector.disable(command.chat_id)
        logger.debug("GC disabled")
        self._reply(
            command,
            "Garbage collector disabled - "
            "new messages won't be removed automatically.",
            reply_markup=self._get_remove_keyboard(),
        )

    def process_cancel(self, command: Command) -> None:
        cancelled = self.collector.cancel(command.chat_id)
        self._reply(
            command, f"Cancelled removal of {cancelled} pending messages."
        )

    def process_retry(self, command: Command) -> None:
        max_attempts = next(iter(command.params_clean), None)
        count_failed = self.collector.count_failed(command.chat_id, max_attempts)

        if not count_failed:
            self._reply(command, "No failed messages found, not re-trying.")
            return

        self._reply(command, f"Attempting to delete {count_failed} failed message(s).")

        self.client.send_chat_action(command.chat_id, "typing")
        self.collector.retry(command.chat_id, max_attempts)

    def process_status(self, command: Command) -> None:
        status = self.collector.status(command.chat_id)
        status.update(self.status())
        status_str = _format_status(status)
        self._reply(command, f"Status: {status_str}")

    def process_ping(self, command: Command) -> None:
        self._reply(command, f"pong")

    def process_github(self, command: Command) -> None:
        self._reply(
            command, f"https://github.com/longedok/gcbot", disable_web_page_preview=True
        )

    def process_help(self, command: Command) -> None:
        self._reply(command, HELP)

    def process_noop(self, command: Command) -> None:
        self._reply(
            command,
            "Aborting, no settings changed.",
            reply_markup=self._get_remove_keyboard(),
        )

    def _get_uptime(self) -> timedelta:
        return datetime.now() - self.start_at

    def status(self) -> dict[str, Any]:
        uptime = self._get_uptime()
        return {
            "bot_uptime": format_interval(uptime),
        }


def _format_status(status: dict[str, Any]) -> str:
    return json.dumps(status, indent=4)

