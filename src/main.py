#!/usr/bin/env python3
from __future__ import annotations

import os
import logging
from typing import TYPE_CHECKING, Union, Mapping, Any

from db import init_storage
from bot import Bot
from client import Client
from privacy import redacted_dict_copy, redact_bot_token
from collector import GarbageCollector

if TYPE_CHECKING:
    from logging import LogRecord


LoggingArgs = Union[Mapping[str, Any], tuple]


class CustomFormatter(logging.Formatter):
    def _redact_logging_args(self, args: LoggingArgs) -> LoggingArgs:
        if isinstance(args, dict):
            return redacted_dict_copy(args)
        else:
            clean_args: list[Any] = []
            for arg in args:
                if isinstance(arg, dict):
                    clean_args.append(redacted_dict_copy(arg))
                elif isinstance(arg, str):
                    clean_args.append(redact_bot_token(arg))
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
        record.args = self._redact_logging_args(record.args)
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

