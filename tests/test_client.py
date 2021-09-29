import pytest
from requests.exceptions import Timeout

from client import BASE_URL, Client

CHAT_ID = -593555199

UPDATE = {
    "update_id": 360316438,
    "message": {
        "message_id": 125,
        "from": {
            "id": 427258479,
            "is_bot": False,
            "first_name": "Иван",
            "username": "iivanov",
        },
        "chat": {
            "id": CHAT_ID,
            "title": "Bot Test (dev)",
            "type": "group",
            "all_members_are_administrators": True,
        },
        "date": 1612207828,
        "text": "Hello World!",
    },
}


class TestClient:
    @pytest.fixture
    def client(self):
        return Client()

    def test_get_updates(self, client, requests_mock):
        requests_mock.get(
            f"{BASE_URL}/getUpdates",
            json={
                "ok": True,
                "result": [UPDATE],
            },
        )
        updates = client.get_updates()
        assert updates == [UPDATE]

    def test_get_updates_timeout(self, client, requests_mock):
        requests_mock.get(f"{BASE_URL}/getUpdates", exc=Timeout)
        updates = client.get_updates()
        assert updates == []
