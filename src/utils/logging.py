from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Mapping, Union

from .privacy import redact_bot_token, redacted_dict_copy

if TYPE_CHECKING:
    from logging import LogRecord


LoggingArgs = Union[Mapping[str, Any], tuple]


class CustomFormatter(logging.Formatter):
    def _redact_logging_args(self, args: LoggingArgs) -> LoggingArgs:
        if isinstance(args, dict):
            return redacted_dict_copy(args)
        else:
            clean_args: list[Any] = []
            for arg in args:
                if isinstance(arg, dict):
                    clean_args.append(redacted_dict_copy(arg))
                elif isinstance(arg, str):
                    clean_args.append(redact_bot_token(arg))
                else:
                    clean_args.append(arg)
            return tuple(clean_args)

    def _shorten_module_name(self, name: str) -> str:
        parts = name.split(".")
        if len(parts) > 1:
            parts_short = []
            for part in parts[:-1]:
                parts_short.append(part[:1])
            return ".".join(parts_short + parts[-1:])
        return name

    def format(self, record: LogRecord) -> str:
        record.name = self._shorten_module_name(record.name)
        record.args = self._redact_logging_args(record.args)
        return super().format(record)
