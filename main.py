#!/usr/bin/env python3
import os
import logging

from db import init_storage
from bot import Bot
from client import Client
from collector import GarbageCollector


def init_logging():
    env = os.environ.get("ENVIRONMENT", "dev")
    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d %(levelname)-5s %(name)s > %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.DEBUG,
    )
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

