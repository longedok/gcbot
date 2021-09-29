from __future__ import annotations

import json
from logging import getLogger
from typing import TYPE_CHECKING, Any, Type, cast

from client import Client
from db import session
from entities import CallbackQuery, Message
from settings import get_settings
from utils.formatting import format_interval
from utils.keyboards import get_remove_keyboard, get_ttl_buttons
from utils.table import Table
from validators import FwdValidator, GcValidator, RetryValidator

if TYPE_CHECKING:
    from bot_context import BotContext
    from collector import GarbageCollector
    from entities import Command
    from validators import Validator


logger = getLogger(__name__)


class CommandHandlerRegistry(type):
    command_handlers: dict[str, Type[CommandHandler]] = {}
    callback_handlers: dict[str, Type[CommandHandler]] = {}

    def __new__(cls, name, bases, dct) -> CommandHandlerRegistry:
        handler_cls = super().__new__(cls, name, bases, dct)
        if hasattr(handler_cls, "command_str"):
            cls.command_handlers[handler_cls.command_str] = handler_cls
        if hasattr(handler_cls, "callback_type"):
            cls.callback_handlers[handler_cls.callback_type] = handler_cls
        return handler_cls

    @classmethod
    def get_for_command_str(cls, command_str: str) -> Type[CommandHandler] | None:
        return cls.command_handlers.get(command_str)

    @classmethod
    def get_for_callback_type(cls, callback_type: str) -> Type[CommandHandler] | None:
        return cls.callback_handlers.get(callback_type)

    @classmethod
    def get_public_handlers(cls) -> list[Type[CommandHandler]]:
        handlers = []
        for handler_class in cls.command_handlers.values():
            if getattr(handler_class, "short_description", None):
                handlers.append(handler_class)

        return handlers


class CommandHandler(metaclass=CommandHandlerRegistry):
    validator_class: Type[Validator] | None = None
    validator: Validator | None

    def __init__(
        self, client: Client, collector: GarbageCollector, context: BotContext
    ) -> None:
        self.client = client
        self.collector = collector
        self.context = context
        if self.validator_class:
            self.validator = self.validator_class()
        else:
            self.validator = None

    def process(self, message: Message) -> None:
        raise NotImplementedError

    def validate(self, command: Command) -> None:
        if self.validator:
            self.validator.validate(command)


class GcHandler(CommandHandler):
    command_str = "gc"
    short_description = "Enable automatic removal of messages"
    validator_class = GcValidator

    def process(self, message: Message) -> None:
        command = message.command
        assert command

        if not command.params_clean:
            self.client.reply(
                message,
                "Please choose an expiration time for new messages",
                reply_markup=self._get_keyboard(),
            )
            return

        ttl = command.params_clean[0]

        self.collector.enable(message.chat.id, ttl)
        logger.debug("GC enabled")

        self.client.reply(
            message,
            f"Garbage collector enabled - automatically removing all new messages "
            f"after {ttl} seconds.",
            reply_markup=get_remove_keyboard(),
        )

    @staticmethod
    def _get_keyboard() -> dict:
        buttons = get_ttl_buttons("gc")
        buttons.append(
            [{"text": "/gcoff - disable GC"}, {"text": "/noop - cancel"}],
        )

        return {
            "keyboard": buttons,
            "one_time_keyboard": True,
            "selective": True,
        }


class GcOffHandler(CommandHandler):
    command_str = "gcoff"
    short_description = "Disable automatic removal of messages."

    def process(self, message: Message) -> None:
        self.collector.disable(message.chat.id)
        logger.debug("GC disabled")
        self.client.reply(
            message,
            "Garbage collector disabled - "
            "new messages won't be removed automatically.",
            reply_markup=get_remove_keyboard(),
        )


class CancelHandler(CommandHandler):
    command_str = "cancel"
    short_description = "Cancel removal of all pending messages."

    def process(self, message: Message) -> None:
        cancelled = self.collector.cancel(message.chat.id)
        self.client.reply(
            message, f"Cancelled removal of {cancelled} pending messages."
        )


class RetryHandler(CommandHandler):
    command_str = "retry"
    short_description = "Re-try failed deletions."
    validator_class = RetryValidator

    def process(self, message: Message) -> None:
        command = message.command
        assert command

        max_attempts = next(iter(command.params_clean), None)
        count_failed = self.collector.count_failed(message.chat.id, max_attempts)

        if not count_failed:
            self.client.reply(message, "No failed messages found, not re-trying.")
            return

        self.client.reply(
            message, f"Attempting to delete {count_failed} failed message(s)."
        )

        self.client.send_chat_action(message.chat.id, "typing")
        self.collector.retry(message.chat.id, max_attempts)


class QueueHandler(CommandHandler):
    command_str = "queue"
    short_description = "Shows the IDs of messages to be removed next."
    callback_type = "queue"

    def process(self, message: Message) -> None:
        records = self.collector.get_removal_queue(message.chat.id)
        table = Table(records, 1)
        self.client.reply(message, table.build(), **table.get_reply_markup())

    def process_callback(self, callback: CallbackQuery) -> None:
        records = self.collector.get_removal_queue(callback.chat_id)
        page = callback.data.get("page")
        table = Table(records, cast(int, page))

        self.client.edit_message_text(
            callback.chat_id,
            callback.message_id,
            table.build(),
            parse_mode="HTML",
            **table.get_reply_markup(),
        )

        self.client.answer_callback_query(callback.id)


class FwdHandler(CommandHandler):
    command_str = "fwd"
    short_description = "Enable automatic removal of forwards from channels."
    validator_class = FwdValidator

    def process(self, message: Message) -> None:
        command = message.command
        assert command

        if not command.params_clean:
            self.client.reply(
                message,
                "Please choose an expiration time for forwarded messages",
                reply_markup=self._get_keyboard(),
            )
            return

        ttl = command.params_clean[0]

        settings = get_settings(message.chat.id)
        settings.forwards_ttl = ttl
        session.add(settings)
        session.commit()

        logger.debug("Forwards removal enabled")

        if ttl > 0:
            self.client.reply(
                message,
                f"Automatic removal of forwarded messages enabled. Removing forwards "
                f"after {ttl} seconds.",
                reply_markup=get_remove_keyboard(),
            )
        else:
            self.client.reply(
                message,
                f"Automatic removal of forwarded messages disabled.",
                reply_markup=get_remove_keyboard(),
            )

    @staticmethod
    def _get_keyboard() -> dict[str, Any]:
        buttons = get_ttl_buttons("fwd")
        buttons.append(
            [{"text": "/fwd 0"}, {"text": "/noop - cancel"}],
        )

        return {
            "keyboard": buttons,
            "one_time_keyboard": True,
            "selective": True,
        }


class StatusHandler(CommandHandler):
    command_str = "status"
    short_description = "Get current status."

    def process(self, message: Message) -> None:
        status = self.collector.status(message.chat.id)
        status.update(
            {
                "uptime": format_interval(self.context.get_uptime()),
            }
        )
        status_str = self._format_status(status)
        self.client.reply(message, f"Status: {status_str}")

    @staticmethod
    def _format_status(status: dict[str, Any]) -> str:
        return json.dumps(status, indent=4)


class PingHandler(CommandHandler):
    command_str = "ping"
    short_description = 'Sends "pong" in response.'

    def process(self, message: Message) -> None:
        self.client.reply(message, f"pong")


class GithubHandler(CommandHandler):
    command_str = "github"
    short_description = 'Sends "pong" in response.'

    def process(self, message: Message) -> None:
        self.client.reply(
            message,
            f"https://github.com/longedok/gcbot",
            disable_web_page_preview=True,
        )


class HelpHandler(CommandHandler):
    command_str = "help"
    short_description = "Display help message."

    HELP = """
This bot allows you to set an expiration time for all new messages in a group chat. It supports the following commands:

<b>Control commands</b>
/gc [<i>time_interval</i>] - Enable automatic removal of messages after <i>time_interval</i>. E.g., the command <code>/gc 1h</code> will result in all new messages being removed when they become 1 hour old.

The <i>time_interval</i> parameter accepts an integer value of seconds between 0 and 172800 or a string describing a time interval, such as "15 minutes" or "1h30m", up to the maximum value of "2 days". If the parameter is not provided, a UI with the default time intervals will be presented.

/gcoff - Disable automatic removal of messages.

/fwd [<i>time_interval</i>] - Enable automatic removal of forwarded messages from <i>certain</i> channels. Use command <code>/fwd 0</code> to disable.

/cancel - Cancel removal of all pending messages.

/retry [<i>max_attempts</i>] - Try to remove messages that failed to be removed automatically. If the <i>max_attempts</i> parameter is specified, messages that were already re-tried more than <i>max_attempts</i> times won't be re-tried.

<b>Info commands</b>
/queue - Shows IDs of messages to be removed next.
/status - Get current status.
/github - Link to the bot's source code.
/ping - Sends "pong" in response.
/help - Display help message.

<b>Quick tags</b>
You can also include a hashtag specifying a time interval inside the message's text, to override the global expiration time for a single message. E.g.: "Hi all #5m" - this message will be removed in 5 minutes, ignoring the global expiration time setting.

The same restrictions apply to time interval in tags as with the global <i>time_interval</i> setting, but the bot will silently ignore invalid intervals in tags.
"""

    def process(self, message: Message) -> None:
        self.client.reply(message, self.HELP)


class NoopHandler(CommandHandler):
    command_str = "noop"

    def process(self, message: Message) -> None:
        self.client.reply(
            message,
            "Aborting, no settings changed.",
            reply_markup=get_remove_keyboard(),
        )
