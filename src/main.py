#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Mapping, Union

from bot import Bot
from client import Client
from collector import GarbageCollector
from db import init_storage
from utils.logging import CustomFormatter


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
