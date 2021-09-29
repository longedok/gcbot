from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import requests
from requests.exceptions import Timeout

if TYPE_CHECKING:
    from requests import Response

    from entities import Message

logger = logging.getLogger(__name__)

TOKEN = os.environ["TOKEN"]
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"


@dataclass
class APIResponse:
    data: dict = field(repr=False)
    text: str | None
    status: int
    response: Response | None = field(repr=False, default=None)
    timeout: bool = field(default=False)

    @property
    def ok(self) -> bool:
        if self.data and self.data.get("ok"):
            return True
        return False

    def get_result(self) -> dict | list | None:
        if self.data:
            return self.data.get("result")
        return None

    @classmethod
    def from_response(cls, response: Response) -> APIResponse:
        try:
            data = response.json()
        except ValueError:
            data = {}
            logger.error("Invalid json in API response: %s", response.text)

        if not (200 <= response.status_code < 300):
            logger.error(
                "Got non-2xx response: %s %s",
                response.status_code,
                response.text,
            )

        return cls(data, response.text, response.status_code, response=response)

    @classmethod
    def from_timeout(cls) -> APIResponse:
        return cls({}, None, 0, timeout=True)

    def raise_for_status(self) -> None:
        if self.response:
            self.response.raise_for_status()


class Client:
    POLL_INTERVAL = 60
    DEFAULT_TIMEOUT = 5

    def __init__(self, last_update_id: int | None = None) -> None:
        self.last_update_id = last_update_id
        self.headers = {"Content-Type": "application/json"}

    def _prepare_params(self, request_params: dict) -> dict:
        headers = {}
        headers.update(self.headers)
        headers.update(request_params.pop("headers", {}))

        params = {
            "headers": headers,
            "timeout": self.DEFAULT_TIMEOUT,
        }
        params.update(request_params)

        return params

    def _post(self, url: str, data: dict, **request_params: Any) -> APIResponse:
        params = self._prepare_params(request_params)

        try:
            response = requests.post(url, json=data, **params)
        except Timeout:
            return APIResponse.from_timeout()

        api_response = APIResponse.from_response(response)
        logger.debug("POST response: %s", api_response)
        return api_response

    def _get(
        self,
        url: str,
        params: dict[str, Any],
        **request_params: Any,
    ) -> APIResponse:
        full_request_params = self._prepare_params(request_params)

        try:
            response = requests.get(url, params=params, **full_request_params)
        except Timeout:
            return APIResponse.from_timeout()

        return APIResponse.from_response(response)

    @property
    def offset(self) -> int | None:
        return self.last_update_id + 1 if self.last_update_id else None

    def get_updates(self) -> list[dict]:
        response = self._get(
            f"{BASE_URL}/getUpdates",
            params={
                "timeout": self.POLL_INTERVAL,
                "offset": self.offset,
            },
            timeout=self.POLL_INTERVAL + 5,
        )

        # don't fail silently to avoid generating lots of requests in the polling loop
        response.raise_for_status()

        if not response.ok:
            logger.error("getUpdates got non-ok response: %s", response)
            return []  # TODO: raise an exception

        if updates := (response.get_result() or []):
            last_update = updates[-1]
            self.last_update_id = last_update["update_id"]

        return cast(list, updates)

    def reply(self, message: Message, text: str, **kwargs: Any) -> None:
        logger.debug("Replying to chat %s: %r", message.chat.id, text)

        self.post_message(
            message.chat.id,
            text,
            reply_to_message_id=message.message_id,
            **kwargs,
        )

    def post_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        **extra_params: Any,
    ) -> APIResponse:
        body = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        body.update(extra_params)

        return self._post(f"{BASE_URL}/sendMessage", body)

    def delete_message(self, chat_id: int, message_id: int) -> APIResponse:
        body = {
            "chat_id": chat_id,
            "message_id": message_id,
        }

        return self._post(f"{BASE_URL}/deleteMessage", body)

    def send_chat_action(self, chat_id: int, action: str) -> APIResponse:
        body = {
            "chat_id": chat_id,
            "action": action,
        }

        return self._post(f"{BASE_URL}/sendChatAction", body)

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        **extra_params: Any,
    ) -> APIResponse:
        body = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        body.update(extra_params)

        return self._post(f"{BASE_URL}/editMessageText", body)

    def answer_callback_query(
        self,
        callback_query_id: int,
        **extra_params: Any,
    ) -> APIResponse:
        body = {
            "callback_query_id": callback_query_id,
        }
        body.update(extra_params)

        return self._post(f"{BASE_URL}/answerCallbackQuery", body)

    def set_my_commands(self, commands: list[dict[str, str]]) -> APIResponse:
        return self._post(f"{BASE_URL}/setMyCommands", {"commands": commands})
