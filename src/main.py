#!/usr/bin/env python3
from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING, Any, Mapping, Union
from copy import deepcopy

from db import init_storage
from bot import Bot
from client import Client
from collector import GarbageCollector

if TYPE_CHECKING:
    from logging import LogRecord


REDACTED_FIELDS = [
    "message.from.id",
    "message.from.first_name",
    "message.from.last_name",
    "message.from.username",
    "message.text",
]


def redact(data: dict, parent: str | None = None) -> None:
    for k, v in data.items():
        path = (f"{parent}." if parent else "") + k
        if isinstance(v, dict):
            redact(v, path)
        if path in REDACTED_FIELDS:
            data[k] = "*" * 3


def redacted_copy(data: dict) -> dict:
    dict_copy = deepcopy(data)
    redact(dict_copy)
    return dict_copy


LoggingArgs = Union[Mapping[str, Any], tuple]


class CustomFormatter(logging.Formatter):
    def _redact_args(self, args: LoggingArgs) -> LoggingArgs:
        if isinstance(args, dict):
            return redacted_copy(args)
        else:
            clean_args: list[Any] = []
            for arg in args:
                if isinstance(arg, dict):
                    clean_args.append(redacted_copy(arg))
                else:
                    clean_args.append(arg)
            return tuple(clean_args)

    def _shorten_module_name(self, name: str) -> str:
        parts = name.split(".")
        if len(parts) > 1:
            parts_short = []
            for part in parts[:-1]:
                parts_short.append(part[:1])
            return ".".join(parts_short + parts[-1:])
        return name

    def format(self, record: LogRecord) -> str:
        record.name = self._shorten_module_name(record.name)
        record.args = self._redact_args(record.args)
        return super().format(record)


def init_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)-5s %(name)-16s > %(message)s",
        level=logging.DEBUG,
    )

    logger = logging.getLogger()
    for handler in logger.root.handlers:  # type: ignore
        handler.setFormatter(CustomFormatter(handler.formatter._fmt))

    env = os.environ.get("ENVIRONMENT", "dev")
    if env == "dev":
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)


def main() -> None:
    init_logging()
    init_storage()

    client = Client()

    collector = GarbageCollector(client)
    collector.start()

    bot = Bot(client, collector)
    bot.start()


if __name__ == "__main__":
    main()

