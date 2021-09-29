from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Type

import pytimeparse

logger = logging.getLogger(__name__)


@dataclass
class Command:
    command_str: str
    params: list[str]
    username: str
    entity: Entity

    params_clean: list[Any] = field(default_factory=list, init=False)


@dataclass
class Chat:
    id: int
    title: str = field(repr=False)
    type: str

    @classmethod
    def from_json(cls, chat_json: dict) -> Chat:
        chat_id = chat_json["id"]
        title = chat_json["title"]
        chat_type = chat_json["type"]
        return cls(chat_id, title, chat_type)


@dataclass
class ForwardFromChat:
    id: int
    title: str = field(repr=False)
    username: str
    type: str = field(repr=False)

    @classmethod
    def from_json(cls, forwrad_from_chat_json: dict) -> ForwardFromChat:
        chat_id = forwrad_from_chat_json["id"]
        title = forwrad_from_chat_json["title"]
        username = forwrad_from_chat_json["username"]
        chat_type = forwrad_from_chat_json["type"]
        return cls(chat_id, title, username, chat_type)


@dataclass
class Entity:
    offset: int
    length: int
    type: str

    @classmethod
    def from_json(self, entity_json: dict) -> Entity:
        offset = entity_json["offset"]
        length = entity_json["length"]
        type = entity_json["type"]
        return Entity(offset, length, type)


@dataclass
class Message:
    text: str | None = field(repr=False)
    message_id: int
    chat: Chat
    date: int
    entities: list[Entity]
    forward_from_chat: ForwardFromChat | None

    @classmethod
    def from_json(cls, message_json: dict) -> Message:
        text = message_json.get("text")
        message_id = message_json["message_id"]
        chat = Chat.from_json(message_json["chat"])
        date = message_json["date"]

        entities_json = message_json.get("entities", [])
        if entities_json:
            entities = [Entity.from_json(entity) for entity in entities_json]
        else:
            entities = []

        forward_from_chat = None
        if "forward_from_chat" in message_json:
            forward_from_chat = ForwardFromChat.from_json(
                message_json["forward_from_chat"]
            )

        return cls(text, message_id, chat, date, entities, forward_from_chat)

    @cached_property
    def command(self) -> Command | None:
        entities = self.get_entities_by_type("bot_command")
        entity = next(iter(entities), None)

        if not entity:
            return None

        assert self.text

        command_str = self.get_entity_text(entity).lower()
        command_str, _, username = command_str.partition("@")

        params_str = self.text[entity.offset + entity.length + 1 :]
        params = params_str.split() if params_str else []

        return Command(command_str, params, username, entity)

    def get_entities_by_type(self, entity_type: str) -> list[Entity]:
        return [e for e in self.entities if e.type == entity_type]

    def get_entity_text(self, entity: Entity) -> str:
        assert self.text

        offset, length = entity.offset, entity.length
        command_str = self.text[offset + 1 : offset + length].lower()
        return self.text[offset + 1 : offset + length]

    def get_tags(self) -> list[str]:
        entities = self.get_entities_by_type("hashtag")
        tags = []

        for entity in entities:
            tag = self.get_entity_text(entity).lower()
            tags.append(tag)

        return tags


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
