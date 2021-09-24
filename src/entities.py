from __future__ import annotations

from typing import Any, TYPE_CHECKING, ClassVar, Type
from dataclasses import dataclass, field
import json
import logging

import pytimeparse

from utils import valid_ttl


logger = logging.getLogger(__name__)


class ValidationError(Exception):
    def __init__(self, message: str | None) -> None:
        self.message = message


@dataclass
class Command:
    command_str: str
    params: list[str]
    username: str
    offset: int
    message: Message = field(repr=False)

    params_clean: list[Any] = field(default_factory=list, init=False)

    @property
    def chat_id(self) -> int:
        return self.message.chat_id

    def clean_params(self) -> None:
        return None


def clean_ttl(params: list[str]) -> int:
    logger.debug("TTL params: %s", params)
    ttl_str = " ".join(params)
    ttl = pytimeparse.parse(ttl_str)

    if ttl:
        ttl = int(ttl)
    else:
        ttl = int(ttl_str)

    if not valid_ttl(ttl):
        raise ValueError

    return ttl


class GCCommand(Command):
    def clean_params(self) -> None:
        if not self.params:
            return

        try:
            ttl = clean_ttl(self.params)
        except (TypeError, ValueError):
            raise ValidationError(
                "Please provide a \"time to live\" for messages as a valid "
                "integer between 0 and 172800 or a time string such as \"1h30m\" "
                "(\"2 days\" max).\n"
                "E.g. \"/gc 1h\" to start removing new messages after one hour."
            )

        self.params_clean.append(ttl)


class FWDCommand(Command):
    def clean_params(self) -> None:
        if not self.params:
            return

        try:
            ttl = clean_ttl(self.params)
        except (TypeError, ValueError):
            raise ValidationError(
                "Please provide a \"time to live\" for forwarded messages as a valid "
                "integer between 0 and 172800 or a time string such as \"1h30m\" "
                "(\"2 days\" max).\n"
                "E.g. \"/fwd 1h\" to start removing forwarded messages after one hour."
            )

        self.params_clean.append(ttl)


class RetryCommand(Command):
    def clean_params(self) -> None:
        if not self.params:
            return

        try:
            max_attempts = int(self.params[0])
            if not (1 <= max_attempts <= 1000):
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError(
                "Please provide a valid integer between 1 and 1000 for the "
                "<i>max_attempts</i> parameter."
            )

        self.params_clean.append(max_attempts)


@dataclass
class CommandDescriptor:
    command_str: str
    short_description: str
    show_in_autocomplete: bool = True
    command_class: Type[Command] = Command

    @staticmethod
    def get_by_command_str(command_str: str) -> CommandDescriptor | None:
        return COMMAND_STR_TO_DESCRIPTOR.get(command_str)

    @staticmethod
    def get_my_commands() -> list[dict[str, str]]:
        commands = []
        for desc in COMMANDS:
            if desc.show_in_autocomplete:
                commands.append(desc.as_bot_command())
        return commands

    def as_bot_command(self) -> dict[str, str]:
        return {
            "command": self.command_str,
            "description": self.short_description,
        }


COMMANDS = [
    CommandDescriptor(
        "gc", "Enable automatic removal of messages.", command_class=GCCommand,
    ),
    CommandDescriptor("gcoff", "Disable automatic removal of messages."),
    CommandDescriptor(
        "fwd",
        "Enable automatic removal of forwards from channels.",
        command_class=FWDCommand,
    ),
    CommandDescriptor("cancel", "Cancel removal of all pending messages."),
    CommandDescriptor(
        "retry", "Re-try failed deletions.", command_class=RetryCommand,
    ),
    CommandDescriptor("queue", "Shows the IDs of messages to be removed next."),
    CommandDescriptor("status", "Get current status."),
    CommandDescriptor("github", "Link to the bot's source code."),
    CommandDescriptor("ping", "Sends \"pong\" in response."),
    CommandDescriptor("help", "Display help message."),
    CommandDescriptor(
        "noop",
        "Dummy command that clears a reply keyboard.",
        show_in_autocomplete=False
    ),
]
COMMAND_STR_TO_DESCRIPTOR = {desc.command_str: desc for desc in COMMANDS}


@dataclass
class Message:
    text: str | None = field(repr=False)
    message_id: int
    chat_id: int
    date: int
    entities: list[dict]
    forward_username: str | None

    COMMAND_CLASS: ClassVar[dict[str, Type[Command]]] = {
        "gc": GCCommand,
        "retry": RetryCommand,
    }

    @classmethod
    def from_json(cls, message_json: dict) -> Message:
        text = message_json.get("text")
        message_id = message_json["message_id"]
        chat_id = message_json["chat"]["id"]
        entities = message_json.get("entities", [])
        date = message_json["date"]

        if "forward_from_chat" in message_json:
            forward_username = message_json["forward_from_chat"]["username"]
        else:
            forward_username = None

        return cls(text, message_id, chat_id, date, entities, forward_username)

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

        desc = CommandDescriptor.get_by_command_str(command_str)
        cls = desc.command_class if desc else Command
        return cls(command_str, params, username, offset, self)

    def get_tags(self) -> list[str]:
        hashtags = [e for e in self.entities if e["type"] == "hashtag"]
        clean_tags = []

        for entity in hashtags:
            offset, length = entity["offset"], entity["length"]
            tag_clean = self.text[offset + 1:offset + length].lower()
            clean_tags.append(tag_clean)

        return clean_tags


@dataclass
class CallbackQuery:
    id: int
    message_id: int
    chat_id: int
    data: dict

    @classmethod
    def from_json(cls, callback_json: dict) -> CallbackQuery:
        callback_id = callback_json["id"]
        message_id = callback_json["message"]["message_id"]
        chat_id = callback_json["message"]["chat"]["id"]

        try:
            data = json.loads(callback_json["data"])
        except (ValueError, TypeError):
            data = {"raw": callback_json["data"]}

        return cls(callback_id, message_id, chat_id, data)

