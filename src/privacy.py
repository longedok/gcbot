from __future__ import annotations

from typing import Union, Mapping, Any
from copy import deepcopy
import re


REDACTED_FIELDS = [
    "message.from.id",
    "message.from.first_name",
    "message.from.last_name",
    "message.from.username",
    "message.text",
]
MASK = "*" * 3
TOKEN_RE = re.compile(r"/bot([:0-9a-zA-Z]{46})/")


def _redact_bot_token(message: str) -> str:
    if match := TOKEN_RE.search(message):
        start, end = match.span(1)
        return message[:start] + MASK + message[end:]
    return message


def _redact(data: dict, parent: str | None = None) -> None:
    for k, v in data.items():
        path = (f"{parent}." if parent else "") + k
        if isinstance(v, dict):
            _redact(v, path)
        if path in REDACTED_FIELDS:
            data[k] = MASK


def _redacted_copy(data: dict) -> dict:
    dict_copy = deepcopy(data)
    _redact(dict_copy)
    return dict_copy


LoggingArgs = Union[Mapping[str, Any], tuple]


def redact_logging_args(args: LoggingArgs) -> LoggingArgs:
    if isinstance(args, dict):
        return _redacted_copy(args)
    else:
        clean_args: list[Any] = []
        for arg in args:
            if isinstance(arg, dict):
                clean_args.append(_redacted_copy(arg))
            elif isinstance(arg, str):
                clean_args.append(_redact_bot_token(arg))
            else:
                clean_args.append(arg)
        return tuple(clean_args)

