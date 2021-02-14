from __future__ import annotations

from typing import Any, TYPE_CHECKING, ClassVar, Type
from dataclasses import dataclass, field
import json

import pytimeparse

from utils import valid_ttl


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


class GCCommand(Command):
    def clean_params(self) -> None:
        if not self.params:
            return

        ttl_str = " ".join(self.params)

        try:
            ttl = pytimeparse.parse(ttl_str)

            if ttl:
                ttl = int(ttl)
            else:
                ttl = int(ttl_str)

            if not valid_ttl(ttl):
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError(
                "Please provide a \"time to live\" for messages as a valid "
                "integer between 0 and 172800 or a time string such as \"1h30m\" "
                "(\"2 days\" max).\n"
                "E.g. \"/gc 1h\" to start removing new messages after one hour."
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
class Message:
    text: str | None = field(repr=False)
    message_id: int
    chat_id: int
    date: int
    entities: list[dict]

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

        cls = self.COMMAND_CLASS.get(command_str, Command)
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

