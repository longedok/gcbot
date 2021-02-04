#!/usr/bin/env python3
import logging

from db import init_storage
from client import Client
from collector import GarbageCollector
from bot import Bot

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(levelname)-5s %(name)s > %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG,
)
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)


def main() -> None:
    init_storage()

    client = Client()

    collector = GarbageCollector(client)
    collector.start()

    bot = Bot(client, collector)
    bot.start()


if __name__ == "__main__":
    main()

