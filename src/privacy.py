from __future__ import annotations

from typing import Union, Mapping, Any
from copy import deepcopy
import re


REDACTED_FIELDS = [
    "*.from.id",
    "*.from.first_name",
    "*.from.last_name",
    "*.from.username",
    "*.text",
    "*.chat.title",
]
MASK = "*" * 3
TOKEN_RE = re.compile(r"/bot([:0-9a-zA-Z_-]{46})/")


def _redact_bot_token(message: str) -> str:
    if match := TOKEN_RE.search(message):
        start, end = match.span(1)
        return message[:start] + MASK + message[end:]
    return message


def _match_path(path: str, template: str) -> bool:
    parts = template.split(".")
    if parts[0] == "*" and len(parts) > 1:
        ending = ".".join(parts[1:])
        return path.endswith(ending)
    else:
        return path == template


def _redact_dict(data: dict, parent: str | None = None) -> None:
    for k, v in data.items():
        path = (f"{parent}." if parent else "") + k
        if isinstance(v, dict):
            _redact_dict(v, path)
        for template in REDACTED_FIELDS:
            if _match_path(path, template):
                data[k] = MASK
                break


def _redacted_dict_copy(data: dict) -> dict:
    dict_copy = deepcopy(data)
    _redact_dict(dict_copy)
    return dict_copy


LoggingArgs = Union[Mapping[str, Any], tuple]


def redact_logging_args(args: LoggingArgs) -> LoggingArgs:
    if isinstance(args, dict):
        return _redacted_dict_copy(args)
    else:
        clean_args: list[Any] = []
        for arg in args:
            if isinstance(arg, dict):
                clean_args.append(_redacted_dict_copy(arg))
            elif isinstance(arg, str):
                clean_args.append(_redact_bot_token(arg))
            else:
                clean_args.append(arg)
        return tuple(clean_args)

