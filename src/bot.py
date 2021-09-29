from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

import pytimeparse

from bot_context import BotContext
from command_handlers import CommandHandlerRegistry
from db import session
from entities import CallbackQuery, Message
from exceptions import ValidationError
from settings import get_settings
from utils.formatting import format_interval
from utils.validation import valid_ttl

if TYPE_CHECKING:
    from client import Client
    from collector import GarbageCollector

logger = logging.getLogger(__name__)

FORWARD_USERNAMES_TO_DELETE = [
    "tutby_official",
    "mediazona_by",
]


class Bot:
    USERNAME = os.environ.get("BOT_USERNAME", "gcservantbot")

    def __init__(self, client: Client, collector: GarbageCollector) -> None:
        self.client = client
        self.collector = collector
        self.context = BotContext()

    def start(self) -> None:
        self.set_my_commands()
        self.run_polling_loop()

    def set_my_commands(self) -> None:
        logger.info("Setting bot's command list")
        handlers = CommandHandlerRegistry.get_public_handlers()
        commands = []
        for handler in handlers:
            commands.append(
                {
                    "command": handler.command_str,
                    "description": handler.short_description,
                }
            )
        self.client.set_my_commands(commands)

    def run_polling_loop(self) -> None:
        logger.info("Starting the polling loop")
        while True:
            try:
                updates = self.client.get_updates()
            except KeyboardInterrupt:
                logger.info("Exiting...")
                return

            for update in updates:
                self.process_update(update)

            if updates:
                logger.debug("%d update(s) processed", len(updates))

    def process_update(self, update: dict) -> None:
        logger.debug("Processing new update: %s", update)

        if "message" in update:
            message = Message.from_json(update["message"])
            self.process_message(message)
        elif "callback_query" in update:
            callback = CallbackQuery.from_json(update["callback_query"])
            self.process_callback(callback)

    def process_message(self, message: Message) -> None:
        logger.debug("New %s", message)

        if message.forward_from_chat:
            if self.process_forward_message(message):
                return
        elif message.command:
            if self.process_command_message(message):
                return
        elif tags := message.get_tags():
            if self.process_tags(message, tags):
                return

        self.collector.add_message(message)

    def process_callback(self, callback: CallbackQuery) -> None:
        logger.debug("New %s", callback)

        callback_type = callback.data.get("type")
        if callback_type is None:
            logger.error("Received a CallbackQuery with wrong structure: %s", callback)
            return

        handler_class = CommandHandlerRegistry.get_for_callback_type(callback_type)
        if handler_class:
            handler = handler_class(self.client, self.collector, self.context)
            handler.process_callback(callback)

    def process_command_message(self, message: Message) -> bool:
        command = message.command
        assert command

        if command.entity.offset != 0:
            return False

        if command.username and command.username != self.USERNAME:
            logger.debug(
                "Received a command that's meant for another bot: %s@%s",
                command.command_str,
                command.username,
            )
            return False

        handler_class = CommandHandlerRegistry.get_for_command_str(command.command_str)
        if not handler_class:
            self.client.reply(message, f"Unrecognized command: {command.command_str}")
            return False

        handler = handler_class(self.client, self.collector, self.context)
        try:
            handler.validate(command)
        except ValidationError as exc:
            self.client.reply(message, exc.message)
            return True

        handler.process(message)

        return True

    def process_forward_message(self, message: Message) -> bool:
        assert message.forward_from_chat

        if message.forward_from_chat.username not in FORWARD_USERNAMES_TO_DELETE:
            return False

        settings = get_settings(message.chat.id)

        if not settings.forwards_ttl:
            return False

        logger.debug("Found a forward message from the list of undesirable usernames")
        self.collector.add_message(message, settings.forwards_ttl)
        return True

    def process_tags(self, message: Message, tags: list[str]) -> bool:
        ttl = pytimeparse.parse(tags[0])
        if ttl and valid_ttl(ttl):
            self.collector.add_message(message, int(ttl))
            return True
        else:
            return False
