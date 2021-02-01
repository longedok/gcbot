import logging
from main import Bot
from unittest.mock import Mock
import copy

import pytest


CHAT_ID = -593555199


UPDATE = {
    "update_id": 360316438,
    "message": {
        "message_id": 125,
        "from": {
            "id": 427258479,
            "is_bot": False,
            "first_name": "Иван",
            "username": "iivanov"
        },
        "chat": {
            "id": CHAT_ID,
            "title": "Bot Test (dev)",
            "type": "group",
            "all_members_are_administrators": True
        },
        "date": 1612207828,
        "text": "Hello World!",
    }
}


def make_message(text):
    body = copy.deepcopy(UPDATE)
    body["message"]["text"] = text

    if text.startswith("/"):
        command = text.split()[0]
        body["message"]["entities"] = [{
            "offset": 0,
            "length": len(command),
            "type": "bot_command",
        }]

    return body


def add_message(client, text):
    message = make_message(text)
    client.get_updates = Mock(side_effect=[[message], KeyboardInterrupt])
    return message


def get_response(client):
    return client.post_message.call_args.args


@pytest.fixture
def client():
    return Mock()


@pytest.fixture
def collector():
    return Mock()


class TestBot:
    def test_ping(self, client):
        add_message(client, "/ping")
        Bot(client, Mock()).start()

        assert get_response(client) == (CHAT_ID, "pong")

    def test_message(self, client, collector):
        add_message(client, "Hi there!")
        Bot(client, collector).start()

        assert collector.add_message.called

    def test_gc(self, client, collector):
        update = add_message(client, "/gc")
        Bot(client, collector).start()

        response = (
            f"Garbage collector enabled - automatically removing all new messages "
            f"after 86400 seconds."
        )

        assert get_response(client) == (CHAT_ID, response)
        assert collector.enable.call_args.args == (86400,)

    def test_gc_params(self, client, collector):
        update = add_message(client, "/gc 15")
        Bot(client, collector).start()

        response = (
            f"Garbage collector enabled - automatically removing all new messages "
            f"after 15 seconds."
        )

        assert get_response(client) == (CHAT_ID, response)
        assert collector.enable.call_args.args == (15,)

    def test_gc_off(self, client, collector):
        update = add_message(client, "/gcoff")
        Bot(client, collector).start()

        response = (
            "Garbage collector disabled - new messages won't be removed automatically."
        )

        assert get_response(client) == (CHAT_ID, response)
        assert collector.disable.called

