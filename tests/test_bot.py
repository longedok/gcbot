from unittest.mock import Mock
import copy

import pytest

from bot import Bot, HELP

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


def new_message(bot, text):
    message = make_message(text)
    bot.client.get_updates = Mock(side_effect=[[message], KeyboardInterrupt])
    bot.start()
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
    mock.cancel = Mock(return_value=5)
    return mock


class TestBot:
    @pytest.fixture
    def bot(self, client, collector):
        return Bot(client, collector)

    def test_message(self, collector, bot):
        new_message(bot, "Hi there!")
        assert collector.add_message.called

    def test_ping(self, bot):
        new_message(bot, "/ping")
        assert get_response(bot.client) == (CHAT_ID, "pong")

    def test_gc(self, collector, bot):
        new_message(bot, "/gc")

        response = f"Please choose an expiration time for new messages"

        assert get_response(bot.client) == (CHAT_ID, response)

    def test_gc_params(self, collector, bot):
        new_message(bot, "/gc 15")

        response = (
            f"Garbage collector enabled - automatically removing all new messages "
            f"after 15 seconds."
        )

        assert get_response(bot.client) == (CHAT_ID, response)
        assert collector.enable.call_args.args == (CHAT_ID, 15)

    @pytest.mark.parametrize("message", [
        "/gc abcd",
        "/gc -15",
        "/gc 2.34",
        "/gc 345123",
        "/gc qwefno oenf wqoiefn wqefoin",
    ])
    def test_gc_param_validation(self, bot, message):
        new_message(bot, message)

        chat_id, text = get_response(bot.client)

        assert chat_id == CHAT_ID
        assert "valid integer" in text

    def test_gc_off(self, collector, bot):
        new_message(bot, "/gcoff")

        response = (
            "Garbage collector disabled - new messages won't be removed automatically."
        )

        assert get_response(bot.client) == (CHAT_ID, response)
        assert collector.disable.call_args.args == (CHAT_ID,)

    def test_cancel(self, collector, bot):
        new_message(bot, "/cancel")

        response = "Cancelled removal of 5 pending messages."

        assert get_response(bot.client) == (CHAT_ID, response)
        assert collector.cancel.call_args.args == (CHAT_ID,)

    def test_status(self, bot):
        new_message(bot, "/status")

        chat_id, text = get_response(bot.client)

        assert chat_id == CHAT_ID
        assert "Status:" in text

    def test_help(self, bot):
        new_message(bot, "/help")
        assert get_response(bot.client) == (CHAT_ID, HELP)

    def test_username_command(self, bot):
        bot.USERNAME = "gcservantbot"
        new_message(bot, "/ping@gcservantbot")

        assert get_response(bot.client) == (CHAT_ID, "pong")

    def test_invalid_command(self, bot):
        new_message(bot, "/invalid")

        chat_id, text = get_response(bot.client)
        assert chat_id == CHAT_ID
        assert "unrecognized command" in text.lower()

