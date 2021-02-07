from __future__ import annotations

import logging
import os

import requests
from requests.exceptions import Timeout

logger = logging.getLogger(__name__)

TOKEN = os.environ["TOKEN"]
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"


class Client:
    POLL_INTERVAL = 60

    def __init__(self, last_update_id: int | None = None) -> None:
        self.last_update_id = last_update_id
        self.headers = {"Content-Type": "application/json"}

    def _post(self, url: str, data: dict) -> None:
        response = requests.post(url, json=data, headers=self.headers)

        if response.status_code == 200:
            logger.debug("Got response: %s", response.text)
        else:
            logger.error(
                "Got non-200 response: %s %s", response.status_code, response.text
            )

    def _get(
        self,
        url: str,
        params: dict[str, Any],
        silent: bool = True,
        **request_params: Any,
    ) -> dict:
        response = requests.get(
            url,
            params=params,
            headers=self.headers,
            **request_params,
        )

        if not silent:
            response.raise_for_status()

        if response.status_code != 200:
            logger.error(
                "Got non-200 response: %s %s", response.status_code, response.text,
            )
            return {}  # TODO: raise an exception

        try:
            data = response.json()
        except ValueError:
            logger.error("Got invalid json %s", response.text)
            return {}  # TODO: raise an exception

        return data

    @property
    def offset(self) -> int | None:
        return self.last_update_id + 1 if self.last_update_id else None

    def get_updates(self) -> list[dict]:
        try:
            data = self._get(
                f"{BASE_URL}/getUpdates",
                params={
                    "timeout": self.POLL_INTERVAL,
                    "offset": self.offset,
                },
                timeout=self.POLL_INTERVAL + 5,
                silent=False  # don't fail silently to avoid generating a lot of 
                              # requests in the polling loop
            )
        except Timeout:
            logger.error("getUpdates request timed out")
            return []  # TODO: maybe raise an exception

        if not data["ok"]:
            logger.error("getUpdates got non-ok response: %s", data)
            return []  # TODO: raise an exception

        if updates := data.get("result", []):
            last_update = updates[-1]
            self.last_update_id = last_update["update_id"]

        return updates

    def post_message(self, chat_id: int, text: str, parse_mode: str = "HTML") -> None:
        body = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        self._post(f"{BASE_URL}/sendMessage", body)

    def delete_message(self, chat_id: int, message_id: int) -> None:
        body = {
            "chat_id": chat_id,
            "message_id": message_id,
        }

        self._post(f"{BASE_URL}/deleteMessage", body)

