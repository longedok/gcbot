import logging
from main import Bot, HELP
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


def new_message(client, text):
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
    mock = Mock()
    mock.status = Mock(return_value={})
    return mock


class TestBot:
    @pytest.fixture
    def bot(self, client, collector):
        return Bot(client, collector)

    def test_ping(self, client, bot):
        new_message(client, "/ping")
        bot.start()

        assert get_response(client) == (CHAT_ID, "pong")

    def test_message(self, client, collector, bot):
        new_message(client, "Hi there!")
        bot.start()

        assert collector.add_message.called

    def test_gc(self, client, collector, bot):
        new_message(client, "/gc")
        bot.start()

        response = (
            f"Garbage collector enabled - automatically removing all new messages "
            f"after 86400 seconds."
        )

        assert get_response(client) == (CHAT_ID, response)
        assert collector.enable.call_args.args == (86400,)

    def test_gc_params(self, client, collector, bot):
        new_message(client, "/gc 15")
        bot.start()

        response = (
            f"Garbage collector enabled - automatically removing all new messages "
            f"after 15 seconds."
        )

        assert get_response(client) == (CHAT_ID, response)
        assert collector.enable.call_args.args == (15,)

    @pytest.mark.parametrize("message", [
        "/gc abcd",
        "/gc -15",
        "/gc 2.34",
        "/gc 345123",
        "/gc qwefno oenf wqoiefn wqefoin",
    ])
    def test_gc_param_validation(self, client, bot, message):
        new_message(client, message)
        bot.start()

        chat_id, text = get_response(client)

        assert chat_id == CHAT_ID
        assert "valid integer" in text

    def test_gc_off(self, client, collector, bot):
        new_message(client, "/gcoff")
        bot.start()

        response = (
            "Garbage collector disabled - new messages won't be removed automatically."
        )

        assert get_response(client) == (CHAT_ID, response)
        assert collector.disable.called

    def test_status(self, client, bot):
        new_message(client, "/status")
        bot.start()

        chat_id, text = get_response(client)

        assert chat_id == CHAT_ID
        assert "Status:" in text

    def test_help(self, client, bot):
        new_message(client, "/help")
        bot.start()

        assert get_response(client) == (CHAT_ID, HELP)

    def test_invalid_command(self, client, bot):
        new_message(client, "/invalid")
        bot.start()

        chat_id, text = get_response(client)
        assert chat_id == CHAT_ID
        assert "unrecognized command" in text.lower()

