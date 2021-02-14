from unittest.mock import Mock, MagicMock
import random
import copy
from functools import cached_property
from datetime import datetime
import re

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

    re_to_type = {
        r"/\w*\b": "bot_command",
        r"#\w*\b": "hashtag",
    }

    entities = []
    for regexp, entity_type in re_to_type.items():
        for match in re.finditer(regexp, text):
            start, end = match.span()
            entities.append({
                "offset": start,
                "length": end - start,
                "type": entity_type,
            })

    if entities:
        body["message"]["entities"] = entities

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
    mock = MagicMock()
    mock.status = Mock(return_value={})
    mock.cancel = Mock(return_value=5)
    return mock


class FakeMessageRecord:
    @cached_property
    def message_id(self):
        return random.randint(1000, 10000)

    @cached_property
    def delete_after(self):
        return int(datetime.utcnow().timestamp()) + random.randint(100, 1000)


class FakeQuery:
    def __init__(self, records=None) -> None:
        self.records = records if records is not None else []

    def offset(self, *args):
        return self

    def limit(self, *args):
        return self

    def count(self):
        return len(self.records)

    def __iter__(self):
        self.n = 0
        return self

    def __next__(self):
        if self.n < len(self.records):
            record = self.records[self.n]
            self.n += 1
            return record
        else:
            raise StopIteration

    @classmethod
    def populate(cls, n):
        return cls([FakeMessageRecord() for _ in range(n)])


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

    @pytest.mark.parametrize("message", [
        "/gc 15",
        "/gc 15s",
        "/gc 15 seconds",
        "/gc 0.25m",
    ])
    def test_gc_params(self, collector, bot, message):
        new_message(bot, message)

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
        assert bot.collector.retry.call_count == 0

    def test_retry(self, bot):
        bot.collector.count_failed = Mock(return_value=5)
        new_message(bot, "/retry")
        response = "Attempting to delete 5 failed message(s)."

        assert get_response(bot.client) == (CHAT_ID, response)
        assert bot.collector.retry.call_args.args == (CHAT_ID, None)
        assert bot.client.send_chat_action.call_args.args == (CHAT_ID, "typing")

    def test_retry_param(self, bot):
        bot.collector.count_failed = Mock(return_value=5)
        new_message(bot, "/retry 1")
        response = "Attempting to delete 5 failed message(s)."

        assert get_response(bot.client) == (CHAT_ID, response)
        assert bot.collector.retry.call_args.args == (CHAT_ID, 1)
        assert bot.client.send_chat_action.call_args.args == (CHAT_ID, "typing")

    def test_retry_no_failed(self, bot):
        bot.collector.count_failed = Mock(return_value=0)
        new_message(bot, "/retry")
        response = "No failed messages found, not re-trying."
        assert get_response(bot.client) == (CHAT_ID, response)

    @pytest.mark.parametrize("message", [
        "/retry abcd",
        "/retry -15",
        "/retry 2.34",
        "/retry 0",
        "/retry 1001",
        "/retry qwefno oenf wqoiefn wqefoin",
    ])
    def test_retry_param_validation(self, bot, message):
        new_message(bot, message)
        response = (
            "Please provide a valid integer between 1 and 1000 for the "
            "<i>max_attempts</i> parameter."
        )
        assert get_response(bot.client) == (CHAT_ID, response)

    def test_queue(self, bot):
        bot.collector.get_removal_queue = Mock(return_value=FakeQuery.populate(10))
        new_message(bot, "/queue")

        chat_id, text = get_response(bot.client)

        assert chat_id == CHAT_ID
        assert "Message IDs to be deleted next" in text

    def test_queue_empty(self, bot):
        bot.collector.get_removal_queue = Mock(return_value=FakeQuery())
        new_message(bot, "/queue")

        chat_id, text = get_response(bot.client)

        assert chat_id == CHAT_ID
        assert "No messages queued for removal." in text

    def test_status(self, bot):
        new_message(bot, "/status")

        chat_id, text = get_response(bot.client)

        assert chat_id == CHAT_ID
        assert "Status:" in text

    def test_help(self, bot):
        new_message(bot, "/help")
        assert get_response(bot.client) == (CHAT_ID, HELP)

    def test_noop(self, bot):
        new_message(bot, "/noop")
        chat_id, text = get_response(bot.client)
        assert chat_id == CHAT_ID
        assert text.startswith("Aborting")

    def test_username_command(self, bot):
        bot.USERNAME = "gcservantbot"
        new_message(bot, "/ping@gcservantbot")

        assert get_response(bot.client) == (CHAT_ID, "pong")

    def test_invalid_command(self, bot):
        new_message(bot, "/invalid")

        chat_id, text = get_response(bot.client)
        assert chat_id == CHAT_ID
        assert "unrecognized command" in text.lower()

    def test_tags(self, bot):
        new_message(bot, "Hi there #5m #10m #test")

        assert bot.collector.add_message.call_args.args[1] == 5 * 60

    @pytest.mark.parametrize("message", [
        "Hi #whatsupdog",
        "Hi #2days5s",
        "Hi #2secodns",
    ])
    def test_invalid_tags(self, bot, message):
        new_message(bot, message)

        assert bot.collector.add_message.call_args.args[1] is None

